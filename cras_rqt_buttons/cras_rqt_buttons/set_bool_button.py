# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin with a button calling a std_srvs/SetBool service while it is held."""

from cras_rqt_buttons.hold_button_widget import SetBoolButtonWidget
from cras_rqt_common.settings_plugin import SettingsPlugin


class CrasRqtSetBoolButton(SettingsPlugin[SetBoolButtonWidget]):
    """
    An RQt plugin with a large button calling a std_srvs/SetBool service.

    The service is called with ``true`` when the button is pressed and with ``false`` when it is
    released, which is what a push-to-talk button on a robot is good for; ``invert_value`` sends it
    the other way round. The button only becomes enabled once the service is there to answer, it
    shows that the service accepted the press by changing color, and it turns red when a call that
    matters fails.
    """
    def __init__(self, context, plugin_name: str = 'SetBoolButton'):
        super().__init__(context, plugin_name)


def main():
    """Start the plugin in a window of its own."""
    import sys

    from cras_rqt_buttons.button_settings import HoldButtonSettings
    from rqt_gui.main import Main

    main = Main()
    sys.exit(main.main(
        sys.argv, standalone='cras_rqt_buttons/SetBoolButton',
        plugin_argument_provider=HoldButtonSettings.add_arguments))
