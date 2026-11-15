# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin with a button calling a std_srvs/Empty service."""

from cras_rqt_buttons.click_button_widget import EmptyButtonWidget
from cras_rqt_common.settings_plugin import SettingsPlugin


class CrasRqtEmptyButton(SettingsPlugin[EmptyButtonWidget]):
    """
    An RQt plugin with a large button calling a std_srvs/Empty service.

    The button is meant for tasks such as starting or aborting a robot mission: it can be hit with a
    finger, it only becomes enabled once the service is there to answer, and it turns red when the
    service refuses the request or does not answer at all.
    """

    def __init__(self, context, plugin_name: str = 'EmptyButton'):
        super().__init__(context, plugin_name)


def main():
    """Start the plugin in a window of its own."""
    import sys

    from cras_rqt_buttons.button_settings import ClickButtonSettings
    from rqt_gui.main import Main

    main = Main()
    sys.exit(main.main(
        sys.argv, standalone='cras_rqt_buttons/EmptyButton',
        plugin_argument_provider=ClickButtonSettings.add_arguments))
