# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin showing a text coming from a ROS topic."""

from cras_rqt_text.text_widget import TextWidget
from rqt_gui_py.plugin import Plugin


class Text(Plugin):
    """
    An RQt plugin showing a text coming from a std_msgs/String or OverlayText topic.

    The topic, the message type and the text appearance are configured through the standard RQt
    configuration dialog, opened by a gear button in the dock title bar or in the widget corner.
    """

    def __init__(self, context):
        """Create the widget and add it to the RQt window."""
        super().__init__(context)
        self.setObjectName('Text')
        self._widget = TextWidget(context.node)
        if context.serial_number() > 1:
            title = self._widget.windowTitle()
            self._widget.setWindowTitle(f'{title} ({context.serial_number()})')
        context.add_widget(self._widget)

    def shutdown_plugin(self) -> None:
        """Release the ROS interfaces."""
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
