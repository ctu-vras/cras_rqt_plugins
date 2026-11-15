# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The button that is at the heart of the button plugins."""
from typing import override

from cras_rqt_buttons.button_engine import ButtonEngine
from cras_rqt_buttons.button_settings import ServiceButtonSettings
from cras_rqt_common.color import Color
from cras_rqt_common.settings_dialog import SettingsDialog
from cras_rqt_common.settings_widget import SettingsWidget
from python_qt_binding.QtCore import Qt
from python_qt_binding.QtGui import QFontMetricsF, QPalette
from python_qt_binding.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget
from rclpy.node import Node


class ServiceButtonWidget[ServiceType: type, SettingsType: ServiceButtonSettings, DialogType: SettingsDialog](
    SettingsWidget[SettingsType, DialogType]):
    """
    A large button calling a ROS service, meant for a touchscreen as well as for a mouse.

    Everything about how the button looks and how it follows the service is done here: it stays
    disabled until the configured service is found, it is painted the colors the settings say, its
    text is as large as the space it has, and it says in its tool tip what it calls and what it is
    waiting for. What the button does when somebody uses it is left to the subclasses, see
    :class:`~cras_rqt_buttons.click_button_widget.ClickButtonWidget` and
    :class:`~cras_rqt_buttons.hold_button_widget.HoldButtonWidget`.

    The widget never waits for anything: the requests are handed over to
    :class:`~cras_rqt_buttons.button_engine.ButtonEngine`, which reports their outcome through
    signals. While a request is on its way, the button is drawn darker than usual, so that a call
    that takes a long time cannot be mistaken for a button that does nothing. When a call fails, the
    button turns to the color the settings ask for and says what happened in its tool tip.
    """

    MIN_BUTTON_SIZE = 120  # px
    """the smallest size a finger can still hit reliably; the button is not allowed to go below it"""
    FONT_MIN_POINTS = 8.0
    FONT_MAX_POINTS = 96.0
    FONT_MARGIN = 10
    """px, the space around the text the text should not use"""
    CORNER_RADIUS = 12  # px
    FADE = 90
    """out of 255, how see-through the button is when it cannot be used"""
    WORKING_DARKER = 160
    """how much darker (in percent) the button is while it waits for the service to answer"""
    DARK_LIMIT = 128
    """below this lightness (out of 255) a color counts as dark, and the text has to be light"""

    def __init__(self, node: Node, service_type: type[ServiceType], parent: QWidget = None,
                 window_title: str = 'Service Button'):
        super().__init__(parent, window_title)
        self._service_type = service_type
        self._logger = node.get_logger()
        self._resolved_service = None
        self._error = False
        self._error_message = ''
        self._available = False
        self._waiting = False
        self._request_id = 0
        self._last_request_id = 0
        self._last_request = None

        self.setObjectName(f'cras_rqt_buttons__{type(self).__name__}')
        self.setMinimumSize(self.MIN_BUTTON_SIZE, self.MIN_BUTTON_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._button = QPushButton(self.settings().button_text, self)
        self._button.setObjectName(f'{type(self).__name__}__button')
        self._button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # a focus frame only distracts on a touchscreen
        self._button.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._button.setMinimumSize(self.MIN_BUTTON_SIZE, self.MIN_BUTTON_SIZE)
        self._button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)

        self._engine = ButtonEngine[ServiceType](node, service_type, self)
        self._engine.availability_changed.connect(self._service_availability_changed)
        self._engine.call_finished.connect(self.call_finished)
        self.connect_button()

        self._button.setEnabled(False)  # only the engine can say the service is there
        self.apply_settings(self.settings())

    @property
    def button(self) -> QPushButton:
        """The button itself, so that it can be styled and inspected from the outside."""
        return self._button

    def connect_button(self) -> None:
        """Make the button ask for what it is there for; the subclasses say how they are used."""
        self._button.pressed.connect(self._user_acted)

    def _user_acted(self) -> None:
        # Whoever uses the button again does not want to be reminded of the previous failure.
        self._set_error(False, '')

    def shutdown(self) -> None:
        """Stop talking to the service."""
        self._release()
        self._engine.shutdown()
        self._set_waiting(False)

    @override
    def apply_settings(self, settings: SettingsType) -> None:
        """Change the service, the text and the colors according to the given settings."""
        super().apply_settings(settings)
        self._button.setText(settings.button_text)
        self._engine.configure(settings)
        self._resolved_service = self._engine.resolved_service_name()
        self._available = self._engine.is_available()
        self._set_waiting(self._engine.pending_requests() > 0)
        self._update_enabled()
        self._apply_colors()
        self._update_tool_tip()
        self._fit_font_to_text()

    def is_error(self) -> bool:
        """Whether the last service call failed, and the button is therefore red."""
        return self._error

    def is_waiting(self) -> bool:
        """Whether a request was sent and the answer to it has not arrived yet."""
        return self._waiting

    def pending_requests(self) -> int:
        """How many requests were sent and are still waiting for a response."""
        return self._engine.pending_requests()

    def resizeEvent(self, event):
        self._fit_font_to_text()
        super().resizeEvent(event)

    def showEvent(self, event):
        # The size the widget ends up with is often known only when it is about to be shown.
        self._fit_font_to_text()
        super().showEvent(event)

    def send(self, request) -> None:
        """
        Ask the service to do what the given request says, and show that the answer is awaited.

        :param request: the request to send, of the type :attr:`SERVICE_TYPE` asks for
        """
        self._last_request = request
        self._request_id += 1
        self._last_request_id = self._request_id
        # the engine can report the outcome before it returns, so say the button is waiting first
        self._set_waiting(True)
        self._update_tool_tip()  # and what exactly the button is waiting for has just changed
        if not self._engine.send(self._request_id, request):
            self._set_waiting(False)
            self._set_error(True, f'could not call {self._service()}')

    def call_finished(self, request_id: int, success: bool, message: str) -> None:
        """Show what the service answered to the request the button cares about."""
        if request_id == self._last_request_id:
            # only the request that is the valid one now decides what the button looks like
            self._set_waiting(False)
        elif not success and not self._stale_failure_shown():
            self._logger.info(message)
            return
        if not success:
            self._set_error(True, message)

    def _stale_failure_shown(self) -> bool:
        """
        Whether a call that a newer one superseded has something to say about the button.

        A button that is used again before the service answered the previous request has to show the
        outcome of the request that is the valid one now, and nothing else.
        """
        return True

    def _release(self) -> None:
        """
        Forget that the button is being held.

        A button that is only clicked is never held, so there is nothing for it to forget.
        """

    def is_active(self) -> bool:
        """
        Whether the service takes it that the button is being held.

        A button that is only clicked is never held, so it never gets active either.
        """
        return False

    def _active_tip(self) -> str:
        """What the tool tip says while the service accepts what the button says while held."""
        return ''

    def _service(self) -> str:
        """The service the button calls, as the graph sees it."""
        return self._resolved_service or self.settings().service_name

    def _what_it_does(self) -> str:
        """What the tool tip says about the calls the button makes."""
        return f'Calls {self._service()}.'

    def _waiting_tip(self) -> str:
        """What the tool tip says about a call the service has not answered yet."""
        return f'Waiting for {self._service()} to answer.'

    def _colors(self) -> tuple:
        """The color of the button and the color of its text at the moment."""
        settings = self.settings()
        if self._error:
            return settings.error_color, settings.text_color
        return settings.button_color, settings.text_color

    def _service_availability_changed(self, available: bool) -> None:
        self._available = available
        self._update_enabled()
        self._update_tool_tip()

    def _update_enabled(self) -> None:
        self._button.setEnabled(self._available)

    def _set_error(self, error: bool, message: str) -> None:
        if error == self._error and message == self._error_message:
            return
        self._error = error
        self._error_message = message
        self._apply_colors()
        self._update_tool_tip()

    def _set_waiting(self, waiting: bool) -> None:
        """Show that a request is on its way, or stop showing it."""
        if waiting == self._waiting:
            return
        self._waiting = waiting
        self._apply_colors()
        self._update_tool_tip()

    def _waiting_color(self, color: Color | None) -> Color:
        """
        The given color as dark as a button waiting for an answer has to be.

        A button without a color of its own is darkened from the color the Qt style in use paints
        ordinary buttons with, so that even it can show that something is going on.
        """
        if color is None:
            # the palette of the button itself cannot be asked here, because it already knows about
            # the style sheet the button is painted with, and the color would get darker every time
            color = Color(self.palette().color(QPalette.ColorRole.Button))
        return color.darker(self.WORKING_DARKER)

    def _apply_colors(self) -> None:
        """Paint the button, or leave the painting to the Qt style when no color was asked for."""
        background, foreground = self._colors()
        if self._waiting:
            # a request is on its way, and the button shows it by looking pressed in
            background = self._waiting_color(background)
        if background is None and foreground is None:
            # the standard look of a Qt button, which also knows how to fade a disabled one
            self._button.setStyleSheet('')
            return
        if background is not None and background.lightness() < self.DARK_LIMIT:
            # dark colors and black text would be unreadable, and a failure has to be readable too
            if foreground is None or self._error:
                foreground = Color('white')

        normal, pressed, disabled = [], [], []
        if background is not None:
            normal.append(f'background-color: {background.css()};')
            normal.append(f'border: 1px solid {background.darker(140).css()};')
            normal.append(f'border-radius: {self.CORNER_RADIUS}px;')
            pressed.append(f'background-color: {background.darker(130).css()};')
            faded = Color(background.r, background.g, background.b, self.FADE)
            disabled.append(f'background-color: {faded.css()};')
            disabled.append(f'border: 1px solid {faded.darker(120).css()};')
        if foreground is not None:
            normal.append(f'color: {foreground.css()};')
            faded = Color(foreground.r, foreground.g, foreground.b, self.FADE)
            disabled.append(f'color: {faded.css()};')

        name = self._button.objectName()
        self._button.setStyleSheet(
            f'QPushButton#{name} {{{" ".join(normal)}}}'
            f'QPushButton#{name}:pressed {{{" ".join(pressed)}}}'
            f'QPushButton#{name}:disabled {{{" ".join(disabled)}}}')

    def _update_tool_tip(self) -> None:
        tip = self._what_it_does() if self._available else f'Waiting for service {self._service()} to show up.'
        if self.is_active():
            tip = f'{tip}\n{self._active_tip()}'
        if self._waiting:
            tip = f'{tip}\n{self._waiting_tip()}'
        if self._error:
            tip = f'{tip}\nThe last call failed: {self._error_message}'
        self._button.setToolTip(tip)

    def _fit_font_to_text(self) -> None:
        """Make the text as large as the button is, so it can be read from a distance."""
        font = self._button.font()
        if font.pointSizeF() <= 0.0:
            font.setPointSizeF(self.FONT_MIN_POINTS)
        metrics = QFontMetricsF(font)
        height = max(1.0, float(metrics.height()))
        size = (self.height() - 2 * self.FONT_MARGIN) * font.pointSizeF() / height
        text = self._button.text()
        if text:
            advance = (metrics.horizontalAdvance(text) if hasattr(metrics, 'horizontalAdvance')
                       else metrics.width(text))
            if advance > 0:
                width = (self.width() - 2 * self.FONT_MARGIN) * font.pointSizeF() / advance
                size = min(size, width)
        size = min(self.FONT_MAX_POINTS, max(self.FONT_MIN_POINTS, size))
        if abs(size - font.pointSizeF()) > 0.05:
            font.setPointSizeF(size)
            self._button.setFont(font)
