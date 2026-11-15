# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin for controlling a PTZ gimbal-camera."""

from cras_rqt_common.settings_plugin import SettingsPlugin
from cras_rqt_ptz_control.ptz_control_widget import PtzControlWidget


class PtzControl(SettingsPlugin[PtzControlWidget]):
    """
    An RQt plugin to steer a PTZ gimbal-camera with a mouse or with a finger.

    The topics, the service and the command amplitudes are configured through the standard RQt
    configuration dialog, opened by a gear button in the dock title bar or in the widget corner, and
    they can be given on the command line as options named after them.
    """
    def __init__(self, context, plugin_name: str = 'PtzControl'):
        super().__init__(context, plugin_name)
