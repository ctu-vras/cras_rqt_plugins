# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The GUI of the button plugins."""

from cras_rqt_buttons.button_engine import ButtonEngine
from cras_rqt_buttons.button_settings import ButtonSettings, to_color, to_optional_color
from cras_rqt_buttons.button_settings_dialog import ButtonSettingsDialog
from python_qt_binding.QtCore import Qt
from python_qt_binding.QtGui import QColor, QFontMetricsF, QPalette
from python_qt_binding.QtWidgets import QDialog, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from rclpy.node import Node
from std_srvs.srv import Empty, SetBool, Trigger


def _css_color(color: QColor) -> str:
    """The color in a form understood by a Qt style sheet."""
    if color.alpha() == 255:
        return color.name()
    return f'rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})'


class ServiceButtonWidget(QWidget):
    """
    A large button calling a ROS service, meant for a touchscreen as well as for a mouse.

    The button stays disabled until the configured service is found, turns red when the call fails,
    and shows its text as large as the space it has. It never waits for anything: the requests are
    handed over to :class:`cras_rqt_buttons.button_engine.ButtonEngine`, which reports the
    responses through signals.

    While a request is on its way and has not been answered yet, the button is drawn darker than
    usual, so that a call that takes a long time cannot be mistaken for a button that does nothing.
    A button that is held has one more state to show: once the service accepted that the button is
    held, the button is :attr:`active` and is painted in the colors asked for by
    ``active_color`` and ``active_text_color``.
    """

    SERVICE_TYPE = None
    HOLD_MODE = False
    """
    Whether the button is held rather than only clicked, so that what it sends depends on when the operator presses
    it and when they let go of it
    """
    DEFAULTS = ButtonSettings()
    """the settings to start with, overridden by every kind of the button"""
    WINDOW_TITLE = 'Service Button'

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

    def __init__(self, node: Node, parent: QWidget = None):
        super().__init__(parent)
        self._logger = node.get_logger()
        self._settings = type(self).DEFAULTS
        self._button_color = to_optional_color(self._settings.button_color)
        self._text_color = to_optional_color(self._settings.text_color)
        self._error_color = to_color(self._settings.error_color, self.DEFAULTS.error_color)
        self._active_color = to_optional_color(self._settings.active_color)
        self._active_text_color = to_optional_color(self._settings.active_text_color)
        self._resolved_service = None
        self._error = False
        self._error_message = ''
        self._available = False
        self._pressed = False
        self._waiting = False
        self._active = False
        self._request_id = 0
        self._last_request_id = 0
        self._last_request = None

        self.setObjectName(f'cras_rqt_buttons__{type(self).__name__}')
        self.setWindowTitle(type(self).WINDOW_TITLE)
        self.setMinimumSize(self.MIN_BUTTON_SIZE, self.MIN_BUTTON_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._button = QPushButton(self._settings.button_text, self)
        self._button.setObjectName(f'{type(self).__name__}__button')
        self._button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # a focus frame only distracts on a touchscreen
        self._button.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._button.setMinimumSize(self.MIN_BUTTON_SIZE, self.MIN_BUTTON_SIZE)
        self._button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)

        self._engine = ButtonEngine(node, type(self).SERVICE_TYPE, self)
        self._engine.availability_changed.connect(self._service_availability_changed)
        self._engine.call_finished.connect(self._call_finished)
        self._button.pressed.connect(self._button_pressed)
        self._button.released.connect(self._button_released)
        self._button.clicked.connect(self._button_clicked)

        self._button.setEnabled(False)  # only the engine can say the service is there
        self.apply_settings(self._settings)

    @property
    def button(self) -> QPushButton:
        """The button itself, so that it can be styled and inspected from the outside."""
        return self._button

    def settings(self) -> ButtonSettings:
        """The settings the button uses right now."""
        return self._settings

    def is_error(self) -> bool:
        """Whether the last service call failed, and the button is therefore red."""
        return self._error

    def pending_requests(self) -> int:
        """How many requests were sent and are still waiting for a response."""
        return self._engine.pending_requests()

    def is_waiting(self) -> bool:
        """Whether a request was sent and the answer to it has not arrived yet."""
        return self._waiting

    def is_active(self) -> bool:
        """
        Whether the service accepted what the button does while it is being held.

        A button that is only clicked never gets active, it only ever waits for an answer.
        """
        return self._active

    def open_configuration(self) -> None:
        """Let the user change the service the button calls and the way the button looks."""
        title = f'{type(self).WINDOW_TITLE} configuration'
        dialog = ButtonSettingsDialog(self._settings, title, self, hold_mode=self.HOLD_MODE)
        if dialog.exec() != QDialog.Accepted:
            return
        self.apply_settings(dialog.settings())

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Store the settings in the rqt settings."""
        self._settings.save(instance_settings)

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Load the settings from the rqt settings and use them right away."""
        self.apply_settings(ButtonSettings.load(instance_settings, defaults=self.DEFAULTS))

    def apply_settings(self, settings: ButtonSettings) -> None:
        """Change the service, the text and the colors according to the given settings."""
        self._settings = settings
        self._button_color = to_optional_color(settings.button_color)
        self._text_color = to_optional_color(settings.text_color)
        self._error_color = to_color(settings.error_color, self.DEFAULTS.error_color)
        self._active_color = to_optional_color(settings.active_color)
        self._active_text_color = to_optional_color(settings.active_text_color)
        self._button.setText(settings.button_text)
        self._engine.configure(settings)
        self._resolved_service = self._engine.resolved_service_name()
        self._available = self._engine.is_available()
        # whatever the service accepted belongs to the service the button used to call, and so does
        # the request the button was waiting for, which the engine will never answer now
        self._active = False
        self._set_waiting(self._engine.pending_requests() > 0)
        self._update_enabled()
        self._apply_colors()
        self._update_tool_tip()
        self._fit_font_to_text()

    def shutdown(self) -> None:
        """Stop talking to the service."""
        self._pressed = False
        self._engine.shutdown()
        self._set_waiting(False)
        self._active = False

    def hideEvent(self, event):
        if self._pressed:
            # The button vanished under the finger while it was held, so treat it as released.
            self._button_released()
        super().hideEvent(event)

    def resizeEvent(self, event):
        self._fit_font_to_text()
        super().resizeEvent(event)

    def showEvent(self, event):
        # The size the widget ends up with is often known only when it is about to be shown.
        self._fit_font_to_text()
        super().showEvent(event)

    def _button_pressed(self) -> None:
        # The user acts again, so stop complaining about the previous failure right away.
        self._set_error(False, '')
        if not self.HOLD_MODE:
            return
        self._pressed = True
        self._send(self._make_request(True))

    def _button_released(self) -> None:
        if not self.HOLD_MODE:
            return
        self._pressed = False
        self._send(self._make_request(False))
        self._update_enabled()

    def _button_clicked(self) -> None:
        if self.HOLD_MODE:
            return  # in the hold mode, the calls are triggered by pressing and releasing
        self._send(self._make_request(None))

    def _make_request(self, pressed: bool | None):
        """The request to send; ``pressed`` is only meaningful in :attr:`HOLD_MODE`."""
        raise NotImplementedError()

    def _is_held_request(self, request) -> bool:
        """
        Whether the service being asked to accept the given request makes the button active.

        A button that is only clicked is not held at any moment, so there is nothing it could be
        active in.

        :param request: the request the last call sent, or nothing if the button was never used
        """
        return False

    def _send(self, request) -> None:
        self._last_request = request
        self._request_id += 1
        self._last_request_id = self._request_id
        # the engine can report the outcome before it returns, so say the button is waiting first
        self._set_waiting(True)
        self._update_tool_tip()  # and what exactly the button is waiting for has just changed
        if not self._engine.send(self._request_id, request):
            self._set_waiting(False)
            self._set_error(True, f'could not call {self._resolved_service}')

    def _call_finished(self, request_id: int, success: bool, message: str) -> None:
        if request_id == self._last_request_id:
            # only the request that is the valid one now decides what the button looks like
            self._set_active(success and self._is_held_request(self._last_request))
            self._set_waiting(False)
        if success:
            return
        if self.HOLD_MODE and request_id != self._last_request_id:
            # A response to a request that a newer one superseded, e.g. when the button was
            # released before the service managed to answer the press. Say so, but do not turn the
            # button red - it shows the outcome of the request that is the valid one now.
            self._logger.warning(message)
            return
        self._set_error(True, message)

    def _service_availability_changed(self, available: bool) -> None:
        self._available = available
        self._update_enabled()
        self._update_tool_tip()

    def _update_enabled(self) -> None:
        if self._pressed:
            # Never take a held button away from the operator. The release would never arrive and
            # the service would never learn that the button is not pressed anymore.
            return
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

    def _set_active(self, active: bool) -> None:
        """Show that the service accepts what the button does while held, or stop showing it."""
        if active == self._active:
            return
        self._active = active
        self._apply_colors()
        self._update_tool_tip()

    def _colors(self) -> tuple:
        """The color of the button and the color of its text at the moment."""
        if self._error:
            return self._error_color, self._text_color
        if self._active:
            # a color that was not asked for while the button is active is the ordinary one
            return (self._active_color if self._active_color is not None else self._button_color,
                    self._active_text_color if self._active_text_color is not None
                    else self._text_color)
        return self._button_color, self._text_color

    def _waiting_color(self, color: QColor | None) -> QColor:
        """
        The given color as dark as a button waiting for an answer has to be.

        A button without a color of its own is darkened from the color the Qt style in use paints
        ordinary buttons with, so that even it can show that something is going on.
        """
        if color is None:
            # the palette of the button itself cannot be asked here, because it already knows about
            # the style sheet the button is painted with, and the color would get darker every time
            color = QColor(self.palette().color(QPalette.ColorRole.Button))
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
        if background is not None and background.lightness() < 128:
            # dark colors and black text would be unreadable, and a failure has to be readable too
            if foreground is None or self._error:
                foreground = QColor('white')

        normal, pressed, disabled = [], [], []
        if background is not None:
            normal.append(f'background-color: {_css_color(background)};')
            normal.append(f'border: 1px solid {_css_color(background.darker(140))};')
            normal.append(f'border-radius: {self.CORNER_RADIUS}px;')
            pressed.append(f'background-color: {_css_color(background.darker(130))};')
            faded = QColor(background)
            faded.setAlpha(self.FADE)
            disabled.append(f'background-color: {_css_color(faded)};')
            disabled.append(f'border: 1px solid {_css_color(faded.darker(120))};')
        if foreground is not None:
            normal.append(f'color: {_css_color(foreground)};')
            faded = QColor(foreground)
            faded.setAlpha(self.FADE)
            disabled.append(f'color: {_css_color(faded)};')

        name = self._button.objectName()
        self._button.setStyleSheet(
            f'QPushButton#{name} {{{" ".join(normal)}}}'
            f'QPushButton#{name}:pressed {{{" ".join(pressed)}}}'
            f'QPushButton#{name}:disabled {{{" ".join(disabled)}}}')

    def _update_tool_tip(self) -> None:
        service = self._resolved_service or self._settings.service_name
        if not self._available:
            tip = f'Waiting for service {service} to show up.'
        elif self.HOLD_MODE:
            held, released = 'true', 'false'
            if self._settings.invert_value:
                held, released = released, held
            tip = f'Calls {service} with {held} while held and with {released} when released.'
        else:
            tip = f'Calls {service}.'
        if self._waiting:
            tip = f'{tip}\n{self._waiting_tip()}'
        if self._error:
            tip = f'{tip}\nThe last call failed: {self._error_message}'
        self._button.setToolTip(tip)

    def _waiting_tip(self) -> str:
        """What the tool tip says about a call the service has not answered yet."""
        service = self._resolved_service or self._settings.service_name
        return f'Waiting for {service} to answer.'

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


class EmptyButtonWidget(ServiceButtonWidget):
    """A button calling a std_srvs/Empty service, e.g. to start or to stop a robot mission."""

    SERVICE_TYPE = Empty
    DEFAULTS = ButtonSettings(service_name='empty', button_text='Empty')
    WINDOW_TITLE = 'Empty Button'

    def _make_request(self, pressed: bool | None) -> Empty.Request:
        return Empty.Request()


class TriggerButtonWidget(ServiceButtonWidget):
    """A button calling a std_srvs/Trigger service, e.g. to start or to stop a robot mission."""

    SERVICE_TYPE = Trigger
    DEFAULTS = ButtonSettings(service_name='trigger', button_text='Trigger')
    WINDOW_TITLE = 'Trigger Button'

    def _make_request(self, pressed: bool | None) -> Trigger.Request:
        return Trigger.Request()


class PushButtonWidget(ServiceButtonWidget):
    """
    A button calling a std_srvs/SetBool service with true while held and false when released.

    With ``invert_value`` it sends the opposite values, so ``false`` while the button is held and
    ``true`` once the operator lets go of it.

    The button does not leave the operator guessing whether it was noticed at all: it gets darker
    as soon as the press, or later the release, was registered and its request is on its way, and
    stops being dark once the service answers. Once the service accepted that the button is held,
    the button becomes active and is painted in the colors of ``active_color`` and
    ``active_text_color``. That is how the operator tells that the service really took the button,
    and not only that it is still thinking about it.
    """

    SERVICE_TYPE = SetBool
    HOLD_MODE = True
    DEFAULTS = ButtonSettings(service_name='set_bool', button_text='Push to Talk')
    WINDOW_TITLE = 'Push Button'

    def _make_request(self, pressed: bool | None) -> SetBool.Request:
        value = bool(pressed)
        if self._settings.invert_value:
            value = not value
        return SetBool.Request(data=value)

    def _is_held_request(self, request) -> bool:
        held = not self._settings.invert_value
        return bool(getattr(request, 'data', held)) == held

    def _waiting_tip(self) -> str:
        service = self._resolved_service or self._settings.service_name
        if self._is_held_request(self._last_request):
            return f'Registered the press, waiting for {service} to accept it.'
        return f'Registered the release, waiting for {service} to accept it.'
