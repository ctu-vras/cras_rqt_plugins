# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin with a button calling a std_srvs/Trigger service."""

from cras_rqt_buttons.button_widget import TriggerButtonWidget
from cras_rqt_buttons.service_button_plugin import ServiceButtonPlugin, run_standalone


class CrasRqtTriggerButton(ServiceButtonPlugin):
    """
    An RQt plugin with a large button calling a std_srvs/Trigger service.

    The button is meant for tasks such as starting or aborting a robot mission: it can be hit with
    a finger, it only becomes enabled once the service is there to answer, and it turns red when
    the service refuses the request or does not answer at all. It has no value to send, so the
    settings that tell what value to send do not apply to it.
    """

    WIDGET_TYPE = TriggerButtonWidget
    PLUGIN_NAME = 'TriggerButton'


def main():
    """Start the plugin in a window of its own."""
    run_standalone('cras_rqt_buttons/TriggerButton')
