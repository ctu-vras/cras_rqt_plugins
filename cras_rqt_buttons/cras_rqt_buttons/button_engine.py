# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Communication of the button plugins."""

from threading import Lock
from typing import Optional

from cras_rqt_buttons.button_settings import ButtonSettings
from python_qt_binding.QtCore import QObject, QTimer, Signal
from rclpy.clock import Clock
from rclpy.clock_type import ClockType
from rclpy.duration import Duration
from rclpy.node import Node

SERVICE_WATCH_INTERVAL = 0.5  # s, how often to look whether the service appeared or disappeared
TIMEOUT_CHECK_INTERVAL = 100  # ms, how often to look for calls that took too long


class ButtonEngine(QObject):
    """
    Calls a ROS service without ever blocking the caller.

    :attr:`send` hands the request over to rclpy and returns immediately, the responses are
    processed in a callback of the asynchronous call and only forwarded to the GUI thread through
    the signals. Whether the service exists is watched by a timer of the node, so nobody waits for
    a service, a response or an executor anywhere in the GUI.
    """

    availability_changed = Signal(bool)
    """whether the service can be reached; emitted whenever that changes"""

    call_finished = Signal(int, bool, str)
    """request id, whether the call succeeded, and a human readable description of the outcome"""

    def __init__(self, node: Node, service_type, parent: QObject = None):
        super().__init__(parent)
        self._node = node
        self._logger = node.get_logger()
        self._service_type = service_type
        self._settings = ButtonSettings()
        self._service_lock = Lock()
        self._client = None
        self._service_name = None
        self._available = False
        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._watch_timer = None
        self._pending = {}  # request id -> (time of deadline or None, future)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setInterval(TIMEOUT_CHECK_INTERVAL)
        self._timeout_timer.timeout.connect(self._check_timeouts)
        self._shutting_down = False

    def configure(self, settings: ButtonSettings) -> None:
        """Point the engine at the configured service and start watching whether it is there."""
        self._settings = settings
        service_name = settings.service_name.strip()
        with self._service_lock:
            if service_name != self._service_name:
                self._forget_pending()  # the requests of the previous service will never be answered
                self._service_name = service_name
                if self._client is not None:
                    self._node.destroy_client(self._client)
                    self._client = None
                self._set_available(False)
                if service_name:
                    self._client = self._node.create_client(self._service_type, service_name)
            if self._client is not None and self._watch_timer is None:
                self._watch_timer = self._node.create_timer(
                    SERVICE_WATCH_INTERVAL, self._check_availability, clock=self._steady_clock)
        self._check_availability()

    def shutdown(self) -> None:
        """Stop watching the service and release all ROS interfaces."""
        self._shutting_down = True
        with self._service_lock:
            self._timeout_timer.stop()
            if self._watch_timer is not None:
                self._node.destroy_timer(self._watch_timer)
                self._watch_timer = None
            if self._client is not None:
                self._node.destroy_client(self._client)
                self._client = None
            self._service_name = None
            self._set_available(False)
            self._forget_pending()

    def is_available(self) -> bool:
        """Whether the configured service can be reached right now."""
        if self._shutting_down:
            return False
        with self._service_lock:
            return self._available

    def pending_requests(self) -> int:
        """How many requests were sent and are waiting for a response."""
        with self._service_lock:
            return len(self._pending)

    def resolved_service_name(self) -> Optional[str]:
        """The configured service as the graph sees it, so that it can be shown to the user."""
        with self._service_lock:
            if self._client is None:
                return self._service_name
            return self._client.service_name

    def send(self, request_id: int, request) -> bool:
        """
        Send the request to the service and return immediately.

        :param request_id: passed back to :attr:`call_finished` so that the caller can tell which
            request the response belongs to
        :param request: the request to send
        :returns: whether the request was handed over to the service
        """
        if self._shutting_down:
            return False
        with self._service_lock:
            if self._client is None or not self._client.service_is_ready():
                self._logger.warning(f'Service {self._service_name} is not available')
                self._set_available(False)
                return False

            try:
                future = self._client.call_async(request)
            except Exception as exc:
                self._logger.error(f'Calling {self._service_name} failed: {exc}')
                return False
    
            timeout = Duration(seconds=self._settings.response_timeout)
            deadline = self._steady_clock.now() + timeout if timeout.nanoseconds > 0 else None
            self._pending[request_id] = (deadline, future)
            if deadline is not None and not self._timeout_timer.isActive():
                self._timeout_timer.start()
            future.add_done_callback(lambda f: self._handle_response(request_id, f))
            return True

    def _forget_request(self, future) -> None:
        """
        Stop waiting for a response that is not coming anymore.
        
        The caller must hold :attr:`self._service_lock`.
        """
        try:
            if self._client is not None:
                self._client.remove_pending_request(future)
        except Exception:  # the client is gone, so nobody waits for the response either
            pass

    def _forget_pending(self) -> None:
        """
        Drop all in-flight requests.
        
        The caller must hold :attr:`self._service_lock`.
        """
        if self._client is not None:
            for _, future in self._pending.items():
                self._forget_request(future)
        self._pending.clear()
        self._timeout_timer.stop()

    def _check_availability(self) -> None:
        with self._service_lock:
            available = self._client is not None and self._client.service_is_ready()
            self._set_available(available)

    def _set_available(self, available: bool) -> None:
        """
        Set the availability of the service.
        
        The caller must hold :attr:`self._service_lock`.

        :param available: Whether the service is available.
        """
        if available == self._available:
            return
        self._available = available
        self.availability_changed.emit(available)

    def _handle_response(self, request_id: int, future) -> None:
        with self._service_lock:
            if self._pending.pop(request_id, None) is None:
                return  # the request was reported as timed out already
            service_name = self._service_name

        success, message = True, ''
        try:
            response = future.result()
        except Exception as exc:
            success, message = False, f'{self._service_name} call failed: {exc}'
        else:
            if response is None:
                success, message = False, f'{self._service_name} returned no response'
            elif hasattr(response, 'success') and not response.success:
                success = False
                message = f'{self._service_name} refused the request: {response.message}'
        self.call_finished.emit(request_id, success, message)

    def _check_timeouts(self) -> None:
        now = self._steady_clock.now()
        with self._service_lock:
            for request_id, (deadline, future) in list(self._pending.items()):
                if deadline is None or deadline > now:
                    continue
                if self._pending.pop(request_id, None) is None:
                    continue  # the response arrived in the meantime
                self._forget_request(future)
                self.call_finished.emit(
                    request_id, False,
                    f'{self._service_name} did not respond in {self._settings.response_timeout:.1f} s')
            if not self._pending:
                self._timeout_timer.stop()
