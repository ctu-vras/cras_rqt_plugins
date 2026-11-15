# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The widget at the heart of every plugin that can be configured."""

from typing import TypeVar

from cras_rqt_common.settings import SettingsBase
from cras_rqt_common.settings_dialog import SettingsDialog
from cras_rqt_common.typing import resolve_subclass_args
from python_qt_binding.QtWidgets import QDialog, QWidget


class SettingsWidget[SettingsType: SettingsBase, DialogType: SettingsDialog](QWidget):
    """
    A widget that shows what its settings say it should show.

    Everything a settings-driven widget has to do anyway is done here: opening the dialog asking for
    the settings, and storing and restoring them in the settings of RQt.

    The settings are never changed under the widget's hands; they are always replaced by a new
    instance, so that the widget can read whatever it needs from them at any moment.
    """

    # Filled by __init_subclass__
    SETTINGS_TYPE: type[SettingsType]
    DIALOG_TYPE: type[DialogType]

    def __init__(self, parent: QWidget = None, window_title: str = 'Settings'):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self._window_title: str = window_title
        self._settings: SettingsType = self.SETTINGS_TYPE()

    @classmethod
    def __init_subclass__(cls) -> None:
        # This magic copies the type variables into class variables so that we can instantiate the types
        super().__init_subclass__()
        settings_type, dialog_type = resolve_subclass_args(cls, SettingsWidget)

        if not isinstance(settings_type, TypeVar):
            cls.SETTINGS_TYPE = settings_type
        if not isinstance(dialog_type, TypeVar):
            cls.DIALOG_TYPE = dialog_type

    def settings(self) -> SettingsType:
        """The settings the widget uses right now."""
        return self._settings

    def shutdown(self) -> None:
        """
        Stop what the widget does and release the ROS interfaces it uses.

        A widget that only shows what it is told has nothing to stop.
        """
        pass

    def apply_settings(self, settings: SettingsType) -> None:
        """
        Start showing the given settings.

        The widget has to cope with being told to show the settings it already shows. A subclass
        remembers the settings through the parent implementation, and then changes whatever the
        settings speak about.
        """
        self._settings = settings

    def open_configuration(self) -> None:
        """Let the user change the settings, and show them right away if the user agrees to it."""
        dialog = self.DIALOG_TYPE(self._settings, self.dialog_title(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.apply_settings(dialog.settings())

    def dialog_title(self) -> str:
        """What the window asking for the settings says."""
        return f'{self._window_title} configuration'

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Store the settings in the settings of RQt."""
        self._settings.save(instance_settings)

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Load the settings from the settings of RQt and show them right away."""
        self.apply_settings(self.SETTINGS_TYPE.load(instance_settings, defaults=self._settings))
