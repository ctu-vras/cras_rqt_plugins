# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin with a button calling a std_srvs/SetBool service while it is held."""

from cras_rqt_buttons.button_widget import PushButtonWidget
from cras_rqt_buttons.service_button_plugin import ServiceButtonPlugin, run_standalone


class CrasRqtPushButton(ServiceButtonPlugin):
    """
    An RQt plugin with a large button calling a std_srvs/SetBool service.

    The service is called with ``true`` when the button is pressed and with ``false`` when it is
    released, which is what a push-to-talk button on a robot is good for; ``invert_value`` sends it
    the other way round. The button only becomes enabled once the service is there to answer, and
    it turns red when a call that matters fails.
    """

    WIDGET_TYPE = PushButtonWidget
    PLUGIN_NAME = 'PushButton'


def main():
    """Start the plugin in a window of its own."""
    run_standalone('cras_rqt_buttons/PushButton')
