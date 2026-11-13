# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Subscribing to the topic the text plugin shows its text on."""

from cras_rqt_text.text_settings import TextSettings
from python_qt_binding.QtCore import QObject, Signal
from rclpy.clock import Clock
from rclpy.clock_type import ClockType
from rclpy.node import Node
from rclpy.qos import (qos_profile_system_default, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy,
                       QoSDurabilityPolicy)
from rosidl_runtime_py.utilities import get_message

# What a topic nobody publishes on (or nobody publishes in the configured type on) offers.
NO_PUBLISHERS = 'no publishers'


class TextEngine(QObject):
    """
    Brings the text from the configured topic to the GUI.

    The message class is looked up from the configured type name, so the package with the messages
    only has to be installed when its type is the one the user asked for. The QoS of the
    subscription copies what the publishers on the topic offer, because a reliable subscriber would
    never hear a best effort publisher, and a subscriber that does not ask for the latched text
    would never learn it. Until there is nothing to copy, the subscription uses the system default.
    """

    string_text = Signal(str)
    overlay_text = Signal(object)

    DISCOVERY_PERIOD = 0.5  # s, how often to look for publishers on the topic
    DEPTH = 1  # the text is stateful, only the newest message matters

    def __init__(self, node: Node, parent: QObject = None):
        super().__init__(parent)
        self._node = node
        self._logger = node.get_logger()
        self._settings = TextSettings()
        self._message_class = None
        self._subscription = None
        self._topic = None
        self._qos_key = NO_PUBLISHERS
        self._type_warned = False
        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._discovery_timer = node.create_timer(self.DISCOVERY_PERIOD, self._discovery_cb, clock=self._steady_clock)

    def configure(self, settings: TextSettings) -> None:
        """Subscribe to what the user asked for, replacing the previous subscription."""
        self._settings = settings
        self._destroy_subscription()
        self._type_warned = False
        self._message_class = self._load_message_class(settings.message_type)
        self._topic = self._node.resolve_topic_name(settings.topic) if settings.topic else None
        if self._message_class is not None and self._topic:
            self._resubscribe()

    def shutdown(self) -> None:
        """Release the ROS interfaces."""
        self._destroy_subscription()
        self._message_class = None

    def _load_message_class(self, type_name: str):
        """Find the message class behind the configured type name, or nothing if there is none."""
        try:
            return get_message(type_name)
        except Exception as exception:  # a missing or broken message package can fail any way
            self._logger.error(
                f'Cannot load messages of type {type_name}: {exception}. Is the package that defines them installed?',
                throttle_duration_sec=10.0)
            return None

    def _publisher_qos(self):
        """Read the reliability and durability the publishers on the topic offer."""
        reliabilities = set()
        durabilities = set()
        for info in self._node.get_publishers_info_by_topic(self._topic):
            if info.topic_type != self._settings.message_type:
                continue
            profile = info.qos_profile
            reliabilities.add(profile.reliability)
            durabilities.add(profile.durability)
        if not reliabilities or not durabilities:
            return NO_PUBLISHERS

        reliability = QoSReliabilityPolicy.RELIABLE
        if QoSReliabilityPolicy.BEST_EFFORT in reliabilities:
            reliability = QoSReliabilityPolicy.BEST_EFFORT

        durability = QoSDurabilityPolicy.VOLATILE
        if QoSDurabilityPolicy.TRANSIENT_LOCAL in durabilities:
            durability = QoSDurabilityPolicy.TRANSIENT_LOCAL

        return reliability, durability

    def _resubscribe(self) -> None:
        """Recreate the subscription so that it matches what is on the topic right now."""
        key = self._publisher_qos()
        if self._subscription is not None and key == self._qos_key:
            return
        self._destroy_subscription()
        if key is not NO_PUBLISHERS:
            reliability, durability = key
            qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=self.DEPTH,
                             reliability=reliability, durability=durability)
        else:
            qos = qos_profile_system_default
            self._warn_about_type()
        self._subscription = self._node.create_subscription(self._message_class, self._topic, self._text_cb, qos)
        self._qos_key = key

    def _warn_about_type(self) -> None:
        """Warn once that somebody publishes something else than we listen to."""
        if self._type_warned:
            return
        types = {type_name for name, type_names in self._node.get_topic_names_and_types()
                 if name == self._topic for type_name in type_names}
        if types and self._settings.message_type not in types:
            self._type_warned = True
            self._logger.warning(
                f'Topic {self._topic} is published as {', '.join(sorted(types))}, '
                f'not as {self._settings.message_type}.', throttle_duration_sec=10.0)

    def _discovery_cb(self) -> None:
        if self._message_class is None or not self._topic:
            return
        self._resubscribe()

    def _text_cb(self, message) -> None:
        if self._settings.overlay_messages:
            self.overlay_text.emit(message)
        else:
            self.string_text.emit(str(message.data))

    def _destroy_subscription(self) -> None:
        if self._subscription is not None:
            self._node.destroy_subscription(self._subscription)
            self._subscription = None
