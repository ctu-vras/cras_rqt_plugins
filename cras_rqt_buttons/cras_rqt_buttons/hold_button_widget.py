# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The buttons that do their work while they are held, and again once they are let go of."""

from cras_rqt_common.settings_dialog import SettingsDialog
from rclpy.node import Node

from cras_rqt_buttons.button_settings import HoldButtonSettings
from cras_rqt_buttons.button_widget import ServiceButtonWidget
from std_srvs.srv import SetBool


class HoldButtonWidget[ServiceType](ServiceButtonWidget[ServiceType, HoldButtonSettings, SettingsDialog]):
    """
    A button that asks for something when it is pressed and for something else when it is released.

    The button is used twice per press, and each of the two moments has its own request and its own
    answer to wait for. It therefore shows three things apart from being ready: that the press was
    registered and the service has not accepted it yet, that the service accepts what the button
    says while it is held, and that the release was registered and is waiting for its answer. While
    the button waits it looks pressed in, and once the service accepted the press the button is
    active and is painted with the colors the settings ask for, which is how the operator tells that
    the service really took the button rather than still thinking about it.

    A button that is held is never taken away from the operator while it is pressed, and a button
    that vanishes under the finger is treated as released; otherwise the service would never learn
    that the button is not held anymore.
    """

    def __init__(self, node: Node, service_type: type[ServiceType], parent=None, window_title: str = 'Hold Button'):
        # These member vars need to be defined before the super call
        self._pressed = False
        self._accepted = False
        super().__init__(node, service_type, parent, window_title)

    def connect_button(self) -> None:
        # the requests belong to the moments of being held, so the click would only be a third one
        super().connect_button()
        self._button.pressed.connect(self._pressed_down)
        self._button.released.connect(self._let_go)

    def is_active(self) -> bool:
        return self._accepted

    def apply_settings(self, settings: HoldButtonSettings) -> None:
        # whatever the service accepted belongs to the service the button used to call, and it will
        # never answer for it again now
        self._set_accepted(False)
        super().apply_settings(settings)

    def shutdown(self) -> None:
        self._release()
        super().shutdown()

    def hideEvent(self, event):
        if self._pressed:
            # The button vanished under the finger while it was held, so treat it as released.
            self._let_go()
        super().hideEvent(event)

    def call_finished(self, request_id: int, success: bool, message: str) -> None:
        if request_id == self._last_request_id:
            self._set_accepted(success and self._means_held(self._last_request))
        super().call_finished(request_id, success, message)

    def _stale_failure_shown(self) -> bool:
        # A response to a request that a newer one superseded, e.g. when the button was released
        # before the service managed to answer the press. The button shows the outcome of the
        # request that is the valid one now, so the old failure is only worth a line in the log.
        return False

    def _pressed_down(self) -> None:
        self._pressed = True
        self.send(self._hold_request(True))

    def _let_go(self) -> None:
        # The button keeps saying that the service holds it until the release goes through; until
        # then the service still behaves as it would while the button is held.
        self._pressed = False
        self.send(self._hold_request(False))
        self._update_enabled()

    def _release(self) -> None:
        self._pressed = False
        self._set_accepted(False)

    def _set_accepted(self, accepted: bool) -> None:
        """Show that the service accepts that the button is held, or stop showing it."""
        if accepted == self._accepted:
            return
        self._accepted = accepted
        self._apply_colors()
        self._update_tool_tip()

    def _update_enabled(self) -> None:
        if self._pressed:
            # Never take a held button away from the operator. The release would never arrive and
            # the service would never learn that the button is not pressed anymore.
            return
        super()._update_enabled()

    def _hold_request(self, pressed: bool):
        """
        The request for the moment the button was pressed, or for the moment it was let go of.

        The two moments are the whole life of a button that is held, so every kind of such a button
        says what it asks for in each of them.
        """
        raise NotImplementedError()

    def _means_held(self, request) -> bool:
        """
        Whether the service accepting the given request means that it holds what the button asked for.

        :param request: the request the last call sent, or nothing if the button was never used
        """
        raise NotImplementedError()

    def _colors(self) -> tuple:
        settings = self.settings()
        if self._error or not self._accepted:
            return super()._colors()
        # a color that was not asked for while the button is active is the ordinary one
        return (settings.active_color if settings.active_color is not None else settings.button_color,
                settings.active_text_color if settings.active_text_color is not None else settings.text_color)

    def _active_tip(self) -> str:
        return f'{self._service()} accepts that the button is held.'

    def _waiting_tip(self) -> str:
        if self._means_held(self._last_request):
            return f'Registered the press, waiting for {self._service()} to accept it.'
        return f'Registered the release, waiting for {self._service()} to accept it.'


class SetBoolButtonWidget(HoldButtonWidget[SetBool]):
    """
    A button asking a ``std_srvs/srv/SetBool`` service for ``true`` while it is held.

    Once the operator lets go of the button, the service is asked for ``false``, which is how a
    single button on a touchscreen can act as a push-to-talk switch. With ``invert_value`` the
    button asks for the other way round, so ``false`` while it is held and ``true`` afterwards.
    """
    def __init__(self, node: Node, parent=None, window_title: str = 'Set-Bool Button'):
        super().__init__(node, SetBool, parent, window_title)

    def _hold_request(self, pressed: bool) -> SetBool.Request:
        value = bool(pressed)
        if self.settings().invert_value:
            value = not value
        return SetBool.Request(data=value)

    def _means_held(self, request) -> bool:
        held = not self.settings().invert_value
        return bool(getattr(request, 'data', held)) == held

    def _what_it_does(self) -> str:
        held, released = ('true', 'false')
        if self.settings().invert_value:
            held, released = released, held
        return f'Calls {self._service()} with {held} while held and with {released} when released.'
