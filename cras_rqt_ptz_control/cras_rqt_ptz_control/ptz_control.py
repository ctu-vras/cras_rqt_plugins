# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin for controlling a PTZ gimbal-camera."""

from cras_rqt_ptz_control.ptz_control_widget import PtzControlWidget
from rqt_gui_py.plugin import Plugin


class PtzControl(Plugin):
    """
    An RQt plugin to steer a PTZ gimbal-camera with a mouse or with a finger.

    The topics, the service and the command amplitudes are configured through the standard RQt
    configuration dialog, opened by a gear button in the dock title bar or in the widget corner.
    """

    def __init__(self, context):
        """Create the widget and add it to the RQt window."""
        super().__init__(context)
        self.setObjectName('PtzControl')
        self._widget = PtzControlWidget(context.node)
        if context.serial_number() > 1:
            title = self._widget.windowTitle()
            self._widget.setWindowTitle(f'{title} ({context.serial_number()})')
        context.add_widget(self._widget)

    def shutdown_plugin(self) -> None:
        """Stop commanding the gimbal and release the ROS interfaces."""
        self._widget.shutdown()

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Persist the plugin configuration."""
        self._widget.save_settings(plugin_settings, instance_settings)

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Recall the plugin configuration."""
        self._widget.restore_settings(plugin_settings, instance_settings)

    def trigger_configuration(self) -> None:
        """Show the configuration dialog."""
        self._widget.open_configuration()
