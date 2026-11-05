# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Communication of the PTZ control plugin."""

import math

from cras_rqt_ptz_control.ptz_command import PtzCommand
from cras_rqt_ptz_control.ptz_control_settings import PtzControlSettings
from geometry_msgs.msg import TwistStamped
from python_qt_binding.QtCore import QObject, Qt, QTimer, Signal
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_system_default, QoSProfile, ReliabilityPolicy, \
    qos_profile_sensor_data, QoSHistoryPolicy
from rosidl_runtime_py.utilities import get_message
from std_srvs.srv import Trigger

ALLOWED_ZOOM_TYPE_NAMES = (
    'std_msgs/msg/Float32',
    'std_msgs/msg/Float64',
    'std_msgs/msg/Int8',
    'std_msgs/msg/Int16',
    'std_msgs/msg/Int32',
    'std_msgs/msg/Int64',
    'std_msgs/msg/Byte',
    'std_msgs/msg/UInt16',
    'std_msgs/msg/UInt32',
    'std_msgs/msg/UInt64',
)


def get_generic_sub_topic_type_names(node: Node, resolved_topic: str) -> list[str]:
    for n, t in node.get_topic_names_and_types():
        if n == resolved_topic:
            return t
    else:
        return []


class PtzCommandEngine(QObject):
    """
    Publishes PTZ commands and calls the centering service.

    Nothing here blocks: the commands are published synchronously (a non-blocking operation in
    rclpy), the service is called asynchronously and its callback only logs the outcome. The values
    from the zoom topic subscription reach the GUI thread through the :attr:`zoom_updated` signal.
    """

    zoom_updated = Signal(float)

    def __init__(self, node: Node, parent: QObject = None):
        super().__init__(parent)
        self._node = node
        self._logger = node.get_logger()
        self._settings = PtzControlSettings()
        self._held = {}
        self._velocity_pub = None
        self._velocity_topic = None
        self._relative_pub = None
        self._relative_topic = None
        self._zoom_sub = None
        self._zoom_topic = None
        self._zoom_topic_resolved = None
        self._center_client = None
        self._center_service = None
        self._center_pending = False
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._publish_held_velocity)
        self._zoom_sub_timer = node.create_timer(0.25, self._zoom_sub_discovery_cb)

    def configure(self, settings: PtzControlSettings) -> None:
        """Configure the topics, the service and the command rate according to the settings."""
        self._settings = settings
        self._timer.setInterval(max(10, int(round(1000.0 / settings.command_rate_hz))))
        self._velocity_pub, self._velocity_topic = self._ensure_publisher(
            self._velocity_pub, self._velocity_topic, settings.velocity_topic)
        self._relative_pub, self._relative_topic = self._ensure_publisher(
            self._relative_pub, self._relative_topic, settings.relative_topic)
        self._zoom_sub, self._zoom_topic, self._zoom_topic_resolved = self._ensure_generic_subscription(
            self._zoom_sub, self._zoom_topic, self._zoom_topic_resolved, settings.zoom_topic)
        self._center_client, self._center_service = self._ensure_client(
            self._center_client, self._center_service, settings.center_service)

    def shutdown(self) -> None:
        """Stop everything and release all ROS interfaces."""
        self._timer.stop()
        self._held.clear()
        for publisher in (self._velocity_pub, self._relative_pub):
            if publisher is not None:
                self._node.destroy_publisher(publisher)
        if self._zoom_sub is not None:
            self._node.destroy_subscription(self._zoom_sub)
        if self._center_client is not None:
            self._node.destroy_client(self._center_client)
        self._velocity_pub = self._relative_pub = self._center_client = self._zoom_sub = None

    def send_step(self, command: PtzCommand) -> None:
        """Request a single relative motion of the gimbal-camera."""
        if self._relative_pub is None:
            return
        self._relative_pub.publish(self._to_msg(command))

    def start_hold(self, key, command: PtzCommand) -> None:
        """Start sending velocity commands while the button identified by ``key`` is held."""
        self._held[key] = command
        self._publish_held_velocity()
        self._timer.start()

    def stop_hold(self, key) -> None:
        """Stop sending velocity commands for the button identified by ``key``."""
        if key not in self._held:
            return
        del self._held[key]
        self._publish_held_velocity()
        if not self._held:
            self._timer.stop()

    def stop_all(self) -> None:
        """Forget all the buttons that are being held."""
        if not self._held:
            return
        self._held.clear()
        self._timer.stop()
        self._publish_held_velocity()

    def send_center(self) -> None:
        """Ask the gimbal-camera to center itself, without waiting for the response."""
        service = self._settings.center_service
        if self._center_client is None:
            self._logger.warning('No center service configured', throttle_duration_sec=5.0)
            return
        if self._center_pending:
            return
        if not self._center_client.service_is_ready():
            self._logger.warning(f'Service {service} is not available', throttle_duration_sec=5.0)
            return
        self._center_pending = True
        try:
            future = self._center_client.call_async(Trigger.Request())
            future.add_done_callback(self._on_center_done)
        except Exception as exc:
            self._center_pending = False
            self._logger.error(f'{service} call failed: {exc}', throttle_duration_sec=5.0)

    def _on_center_done(self, future) -> None:
        self._center_pending = False
        service = self._settings.center_service
        try:
            response = future.result()
        except Exception as exc:
            self._logger.error(f'{service} call failed: {exc}', throttle_duration_sec=5.0)
            return
        if not response.success:
            self._logger.warning(f'{service} rejected the command: {response.message}',
                                 throttle_duration_sec=5.0)

    def _publish_held_velocity(self) -> None:
        """Send the sum of all held commands, or a stand-still command if no button is held."""
        if self._velocity_pub is None:
            return
        combined = PtzCommand(
            sum((command.pitch for command in self._held.values()), 0.0),
            sum((command.yaw for command in self._held.values()), 0.0),
            sum((command.zoom for command in self._held.values()), 0.0))
        self._velocity_pub.publish(self._to_msg(combined))

    def _to_msg(self, command: PtzCommand) -> TwistStamped:
        msg = TwistStamped()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.twist.angular.y = float(command.pitch)
        msg.twist.angular.z = float(command.yaw)
        msg.twist.linear.x = float(command.zoom)
        return msg

    def _on_zoom(self, msg) -> None:
        if math.isfinite(float(msg.data)):
            if self.zoom_updated:
                self.zoom_updated.emit(float(msg.data))

    def _ensure_publisher(self, publisher, current_topic, wanted_topic):
        if publisher is not None and current_topic == wanted_topic:
            return publisher, current_topic
        if publisher is not None:
            self._node.destroy_publisher(publisher)
        if not wanted_topic:
            return None, None
        publisher = self._node.create_publisher(
            TwistStamped, wanted_topic, qos_profile_system_default)
        return publisher, wanted_topic

    def _ensure_generic_subscription(self, subscription, current_topic, current_topic_resolved, wanted_topic):
        if current_topic == wanted_topic:
            return subscription, current_topic, current_topic_resolved
        if subscription is not None:
            self._node.destroy_subscription(subscription)
        if not wanted_topic:
            return None, None, None
        # the discovery timer will populate the publisher
        return None, wanted_topic, self._node.resolve_topic_name(wanted_topic)

    def _zoom_sub_discovery_cb(self):
        if self._zoom_sub is not None or self._zoom_topic_resolved is None:
            return
        type_names = get_generic_sub_topic_type_names(self._node, self._zoom_topic_resolved)
        if len(type_names) == 0:
            return
        for type_name in type_names:
            if type_name in ALLOWED_ZOOM_TYPE_NAMES:
                # match qos
                for info in self._node.get_publishers_info_by_topic(self._zoom_topic_resolved):
                    qos = info.qos_profile
                    break
                else:
                    return
                sub_qos = QoSProfile(**qos.get_c_qos_profile().to_dict())
                sub_qos.history = QoSHistoryPolicy.KEEP_LAST
                sub_qos.depth = 1
                    
                self._zoom_sub = self._node.create_subscription(
                    get_message(type_name), self._zoom_topic, self._on_zoom, sub_qos)
                self._node.get_logger().info(
                    f'Created zoom subscription for topic {self._zoom_topic} with type {type_name}')
                return

    def _ensure_client(self, client, current_service, wanted_service):
        if client is not None and current_service == wanted_service:
            return client, current_service
        if client is not None:
            self._node.destroy_client(client)
        if not wanted_service:
            return None, None
        return self._node.create_client(Trigger, wanted_service), wanted_service
