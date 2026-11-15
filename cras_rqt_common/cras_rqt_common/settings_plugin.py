# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The RQt plugin around a widget that can be configured."""

import sys
from dataclasses import replace
from typing import get_args, get_origin

from cras_rqt_common.settings_widget import SettingsWidget
from cras_rqt_common.typing import TypeVar, resolve_subclass_args
from rqt_gui_py.plugin import Plugin


class SettingsPlugin[WidgetType: SettingsWidget](Plugin):
    """
    An RQt plugin showing a single :class:`~cras_rqt_common.settings_widget.SettingsWidget`.

    What a plugin has to do beyond showing its widget is done here: putting the widget into the RQt
    window, passing the configuration of the plugin to it, and letting the user change it through the
    standard RQt configuration dialog. The settings can also be given on the command line, as
    options named after them, and what is given there wins.

    The subclass only says which :attr:`WIDGET_TYPE` to show and under which :attr:`PLUGIN_NAME` RQt
    knows it.
    """
    
    # Filled by __init_subclass__
    WIDGET_TYPE: type[WidgetType]
    
    def __init__(self, context, plugin_name: str = 'Plugin'):
        """Create the widget, apply what the command line asked for, and add it to the RQt window."""
        super().__init__(context)
        self.setObjectName(plugin_name)
        self._widget = self.WIDGET_TYPE(context.node)
        settings_type = self._widget.SETTINGS_TYPE
        self._cli_settings, self._cli_overrides = settings_type.from_args(
            context.argv(), defaults=self._widget.settings())
        if self._cli_overrides:
            self._widget.apply_settings(self._cli_settings)
        if context.serial_number() > 1:
            title = self._widget.windowTitle()
            self._widget.setWindowTitle(f'{title} ({context.serial_number()})')
        context.add_widget(self._widget)

    @classmethod
    def __init_subclass__(cls) -> None:
        # This magic copies the type variables into class variables so that we can instantiate the types
        super().__init_subclass__()
        widget_type = resolve_subclass_args(cls, SettingsPlugin)
        
        if not isinstance(widget_type, TypeVar):
            cls.WIDGET_TYPE = widget_type[0]

    def widget(self) -> SettingsWidget:
        """The widget the plugin shows."""
        return self._widget

    def shutdown_plugin(self) -> None:
        """Stop what the widget does and release the ROS interfaces it uses."""
        self._widget.shutdown()

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Persist the configuration of the plugin."""
        self._widget.save_settings(plugin_settings, instance_settings)

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Load the configuration, giving priority to the command line the first time this is called."""
        self._widget.restore_settings(plugin_settings, instance_settings)
        if self._cli_overrides:
            self._widget.apply_settings(replace(self._widget.settings(), **{
                name: getattr(self._cli_settings, name) for name in self._cli_overrides}))
            self._cli_overrides = None

    def trigger_configuration(self) -> None:
        """Show the dialog asking for the settings."""
        self._widget.open_configuration()
