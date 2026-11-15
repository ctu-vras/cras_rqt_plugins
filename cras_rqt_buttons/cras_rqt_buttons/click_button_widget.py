# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The buttons that do their work once every time somebody clicks on them."""

from python_qt_binding.QtWidgets import QWidget
from rclpy.node import Node

from cras_rqt_buttons.button_settings import ClickButtonSettings
from cras_rqt_buttons.button_widget import ServiceButtonWidget
from cras_rqt_common.settings_dialog import SettingsDialog
from std_srvs.srv import Empty, Trigger


class ClickButtonWidget[ServiceType](ServiceButtonWidget[ServiceType, ClickButtonSettings, SettingsDialog]):
    """
    A button calling its service once every time somebody clicks on it.

    The request goes out with the click, i.e. once the operator already let go of the button, so the
    button never holds anything back and the service learns about one call at a time. Until the
    service answers, the button looks pressed in, and it turns to the color the settings ask for
    when the service refuses the request or stays silent for as long as the settings allow.

    Nothing about the response is shown beyond whether it worked; a button that wants to tell what
    the service said is not this kind of a button.
    """

    def connect_button(self) -> None:
        super().connect_button()
        self._button.clicked.connect(self._clicked)

    def _clicked(self) -> None:
        self.send(self._make_request())

    def _make_request(self):
        """The service request to send."""
        return self._service_type.Request()


class EmptyButtonWidget(ClickButtonWidget[Empty]):
    """
    A button calling a ``std_srvs/srv/Empty`` service.

    Meant for tasks such as starting or aborting a robot mission: it can be hit with a finger, and
    the large text makes it hard to miss what it is there for.
    """
    def __init__(self, node: Node, parent: QWidget = None, window_title: str = 'Empty Button'):
        super().__init__(node, Empty, parent, window_title)


class TriggerButtonWidget(ClickButtonWidget[Trigger]):
    """
    A button calling a ``std_srvs/srv/Trigger`` service.

    The response of the service is only looked at as a whole: the text the service returns with the
    response is not shown anywhere, only whether it succeeded.
    """
    def __init__(self, node: Node, parent: QWidget = None, window_title: str = 'Trigger Button'):
        super().__init__(node, Trigger, parent, window_title)
