# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Common RQt plugin around a service-calling button."""

import sys
from dataclasses import replace

from cras_rqt_buttons.button_settings import ButtonSettings
from rqt_gui_py.plugin import Plugin


class ServiceButtonPlugin(Plugin):
    """
    An RQt plugin showing a single large button that calls a ROS service.

    The button is configured through the standard RQt configuration dialog, through the settings
    saved with the perspective, or through the command line options named after the settings
    (``--service-name``, ``--button-text``, ``--button-color``, ``--text-color``,
    ``--error-color``, ``--response-timeout`` and ``--invert-value``). What is given on the command
    line wins.
    """

    WIDGET_TYPE = None
    PLUGIN_NAME = 'ServiceButton'

    def __init__(self, context, widget_type=None):
        """Create the widget, apply the command line settings and add it to the RQt window."""
        super().__init__(context)
        self.setObjectName(type(self).PLUGIN_NAME)
        widget_type = widget_type if widget_type is not None else type(self).WIDGET_TYPE
        self._widget = widget_type(context.node)
        self._cli_settings, self._cli_overrides = ButtonSettings.from_args(
            context.argv(), defaults=self._widget.settings())
        if self._cli_overrides:
            self._widget.apply_settings(self._cli_settings)
        if context.serial_number() > 1:
            title = self._widget.windowTitle()
            self._widget.setWindowTitle(f'{title} ({context.serial_number()})')
        context.add_widget(self._widget)

    def shutdown_plugin(self) -> None:
        """Stop calling the service and release the ROS interfaces."""
        self._widget.shutdown()

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Persist the plugin configuration."""
        self._widget.save_settings(plugin_settings, instance_settings)

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Recall the plugin configuration, keeping whatever was given on the command line."""
        self._widget.restore_settings(plugin_settings, instance_settings)
        if self._cli_overrides:
            self._widget.apply_settings(replace(self._widget.settings(), **{
                name: getattr(self._cli_settings, name) for name in self._cli_overrides}))

    def trigger_configuration(self) -> None:
        """Show the configuration dialog."""
        self._widget.open_configuration()


def run_standalone(plugin_name: str) -> None:
    """
    Run the named plugin of this package in a window of its own.

    The settings of the button can be passed as command line options, see
    :class:`cras_rqt_buttons.button_settings.ButtonSettings`.
    """
    from rqt_gui.main import Main
    main = Main(filename=plugin_name.replace('/', '.'))
    sys.exit(main.main(sys.argv, standalone=plugin_name,
                       plugin_argument_provider=ButtonSettings.add_arguments))
