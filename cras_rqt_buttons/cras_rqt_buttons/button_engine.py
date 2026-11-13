# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Communication of the button plugins."""

from threading import RLock
from typing import Optional

from cras_rqt_buttons.button_settings import ButtonSettings
from python_qt_binding.QtCore import QObject, QTimer, Signal
from rclpy.clock import Clock
from rclpy.clock_type import ClockType
from rclpy.duration import Duration
from rclpy.node import Node

SERVICE_WATCH_INTERVAL = 0.5  # s, how often to look whether the service appeared or disappeared
TIMEOUT_CHECK_INTERVAL = 100  # ms, how often to look for calls that took too long
RETRY_DELAY = 300  # ms, how long to wait before a request that did not work is sent again

REQUEST, ATTEMPTS, DEADLINE, FUTURE = range(4)
"""what the engine keeps about a request that the service has not accepted yet"""


class ButtonEngine(QObject):
    """
    Calls a ROS service without ever blocking the caller.

    :attr:`send` hands the request over to rclpy and returns immediately, the responses are
    processed in a callback of the asynchronous call and only forwarded to the GUI thread through
    the signals. Whether the service exists is watched by a timer of the node, so nobody waits for
    a service, a response or an executor anywhere in the GUI.

    A request that cannot be sent, that is refused or that is not answered in time is sent again
    until the configured number of attempts is used up, and only the failure of the last attempt is
    reported. The request keeps its identifier while it is being sent again, so the caller cannot
    tell the attempts apart.
    """

    availability_changed = Signal(bool)
    """whether the service can be reached; emitted whenever that changes"""

    call_finished = Signal(int, bool, str)
    """request id, whether the call succeeded, and a human readable description of the outcome"""

    _resend_wanted = Signal()
    """a request waits to be sent again, which a timer of the GUI thread takes care of"""

    def __init__(self, node: Node, service_type, parent: QObject = None):
        super().__init__(parent)
        self._node = node
        self._logger = node.get_logger()
        self._service_type = service_type
        self._settings = ButtonSettings()
        # reentrant, because the outcome of a call is reported while the lock is held, and whoever
        # is told about it can ask the engine for something in an answer to that report
        self._service_lock = RLock()
        self._client = None
        self._service_name = None
        self._available = False
        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._watch_timer = None
        self._pending = {}  # request id -> [request, attempts left, deadline or None, future]
        self._to_retry = []  # request ids that did not work and are waiting to be sent again
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setInterval(TIMEOUT_CHECK_INTERVAL)
        self._timeout_timer.timeout.connect(self._check_timeouts)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.setInterval(RETRY_DELAY)
        self._retry_timer.timeout.connect(self._send_again)
        self._resend_wanted.connect(self._start_retry_timer)
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

        The request is sent again as many times as the settings ask for, and only the outcome of
        the last attempt is reported through :attr:`call_finished`.

        :param request_id: passed back to :attr:`call_finished` so that the caller can tell which
            request the response belongs to
        :param request: the request to send
        :returns: whether the engine took the request over and will report its outcome later
        """
        if self._shutting_down:
            return False
        with self._service_lock:
            attempts = max(1, int(self._settings.call_attempts))
            self._pending[request_id] = [request, attempts, None, None]
            self._dispatch(request_id)
        return True

    def _dispatch(self, request_id: int) -> None:
        """
        Hand the request over to the service, or find out that it cannot be sent right now.

        The caller must hold :attr:`_service_lock`.
        """
        waiting = self._pending.get(request_id)
        if waiting is None:
            return  # the request was dropped while it was waiting to be sent again
        if self._client is None or not self._client.service_is_ready():
            self._set_available(False)
            self._attempt_failed(request_id, waiting,
                                 f'Service {self._service_name} is not available')
            return
        try:
            future = self._client.call_async(waiting[REQUEST])
        except Exception as exc:
            self._attempt_failed(request_id, waiting,
                                 f'Calling {self._service_name} failed: {exc}')
            return
        waiting[DEADLINE] = self._deadline()
        waiting[FUTURE] = future
        if waiting[DEADLINE] is not None and not self._timeout_timer.isActive():
            self._timeout_timer.start()
        future.add_done_callback(lambda f: self._handle_response(request_id, f))

    def _deadline(self):
        """
        When a request sent now has to be answered, and nothing if it may take any time.

        The caller must hold :attr:`_service_lock`.
        """
        timeout = Duration(seconds=self._settings.response_timeout)
        return self._steady_clock.now() + timeout if timeout.nanoseconds > 0 else None

    def _attempt_failed(self, request_id: int, waiting, message: str) -> None:
        """
        Send the request once more, or tell the caller that it is not going to work.

        The request stays in :attr:`_pending` while it is being sent again, so that whoever sent it
        keeps waiting for it instead of seeing every attempt separately.

        The caller must hold :attr:`_service_lock`.

        :param request_id: the request the attempt belonged to
        :param waiting: what the engine keeps about that request
        :param message: what went wrong, to be shown to the user once there are no attempts left
        """
        if self._pending.get(request_id) is not waiting:
            return  # a response to the request was reported in the meantime
        if waiting[ATTEMPTS] > 1:
            waiting[ATTEMPTS] -= 1
            self._forget_request(waiting[FUTURE])
            waiting[DEADLINE], waiting[FUTURE] = None, None
            if request_id not in self._to_retry:
                self._to_retry.append(request_id)
            self._logger.warning(f'{message}. Sending the request again, '
                                 f'{waiting[ATTEMPTS]} attempts left.')
            self._resend_wanted.emit()
            return
        self._pending.pop(request_id, None)
        self._forget_request(waiting[FUTURE])
        self.call_finished.emit(request_id, False, message)

    def _start_retry_timer(self) -> None:
        """
        Start waiting for the moment the requests that did not work are sent again.

        The response to a request is processed in a callback of rclpy, in another thread than the
        one the timer of the engine belongs to, so the timer is only started once the signal asking
        for it has arrived in that thread.
        """
        if not self._shutting_down:
            self._retry_timer.start()

    def _send_again(self) -> None:
        """Send once more all the requests that did not work and still have an attempt left."""
        with self._service_lock:
            to_retry, self._to_retry = self._to_retry, []
        for request_id in to_retry:
            with self._service_lock:
                self._dispatch(request_id)

    def _forget_request(self, future) -> None:
        """
        Stop waiting for a response that is not coming anymore.
        
        The caller must hold :attr:`self._service_lock`.
        """
        if future is None:
            return
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
            for waiting in self._pending.values():
                self._forget_request(waiting[FUTURE])
        self._pending.clear()
        self._to_retry.clear()
        self._retry_timer.stop()
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
            waiting = self._pending.get(request_id)
            if waiting is None:
                return  # the request was reported as timed out already
            success, message = self._outcome(future)
            if not success:
                self._attempt_failed(request_id, waiting, message)
                return
            self._pending.pop(request_id, None)
        self.call_finished.emit(request_id, True, '')

    def _outcome(self, future) -> tuple:
        """Whether the response the service gave means that the request got through."""
        try:
            response = future.result()
        except Exception as exc:
            return False, f'{self._service_name} call failed: {exc}'
        if response is None:
            return False, f'{self._service_name} returned no response'
        if hasattr(response, 'success') and not response.success:
            return False, f'{self._service_name} refused the request: {response.message}'
        return True, ''

    def _check_timeouts(self) -> None:
        now = self._steady_clock.now()
        waited = f'{self._settings.response_timeout:.1f} s'
        message = f'{self._service_name} did not respond in {waited}'
        with self._service_lock:
            for request_id, waiting in list(self._pending.items()):
                if waiting[DEADLINE] is None or waiting[DEADLINE] > now:
                    continue  # the request either has all the time in the world or still waits
                self._attempt_failed(request_id, waiting, message)
            if not self._pending:
                self._timeout_timer.stop()
