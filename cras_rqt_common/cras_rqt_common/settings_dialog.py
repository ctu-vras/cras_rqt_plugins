# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The configuration dialog that asks for all settings of a settings class."""

from dataclasses import fields

from cras_rqt_common.settings import SettingsBase
from cras_rqt_common.settings_fields import SettingsField
from python_qt_binding.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

MINIMUM_WIDTH = 420  # px, so that the labels and the tool tips have some room


class SettingsDialog[SettingsType](QDialog):
    """
    A dialog asking for the settings of one settings class.

    The dialog asks for every setting of the settings it is given, in the order the settings are
    declared and under the heading of the section they name, each of them in the widget the setting
    itself knows how to build. A setting added to the settings class therefore shows up in the
    dialog without anything here being touched.

    What the user filled in is read back into a copy of the settings the dialog was given, so the
    settings that :meth:`hidden` keeps out of the dialog keep their value.
    """

    def __init__(self, settings: SettingsType, title: str = 'Configuration', parent: QWidget = None):
        super().__init__(parent)
        self._title: str = title
        self.setWindowTitle(title)
        self._settings: SettingsType = settings
        self._widgets = {}
        self._widgets_by_section = {}

        layout = QVBoxLayout(self)
        headings = 0
        # the settings are shown in the section they name, in the order they are declared
        for section, items in settings.fields_by_section(hidden=self.hidden).items():
            if not items:
                continue
            if section:
                heading = QLabel(f'<b>{section}</b>')
                layout.addWidget(heading)
                # the heading belongs to the section, so it can be enabled along with its settings
                self._widgets_by_section.setdefault(section, {})[f'heading_{headings}'] = heading
                headings += 1
            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for item in items:
                widget = item.create_widget(self, getattr(settings, item.name))
                widget.setToolTip(item.description)
                self._widgets[item.name] = widget
                self._widgets_by_section.setdefault(section, {})[item.name] = widget
                form.addRow(item.label, widget)
            layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(MINIMUM_WIDTH)
        self.setup()

    def settings(self) -> SettingsType:
        """The settings the user filled in."""
        values = {}
        for item in fields(self._settings):
            if item.name in self._widgets and isinstance(item, SettingsField):
                values[item.name] = item.read_widget(self._widgets[item.name])
        return self._settings.with_widget_values(values)

    def widget(self, name: str) -> QWidget:
        """The widget the setting with the given name is edited in."""
        return self._widgets[name]

    def settings_names(self) -> set:
        """The names of the settings the dialog asks for."""
        return set(self._widgets)

    def widgets_of(self, section: str) -> dict:
        """
        The widgets the dialog shows for one of the sections of the settings, their heading included.

        A section is named by the ``section`` the settings field was given.
        """
        return self._widgets_by_section.get(section, {})

    def hidden(self, item: SettingsField) -> bool:
        """
        Whether the dialog leaves the given setting out.

        The setting is left out silently, keeping the value it was opened with, so this is meant for
        settings that only some kinds of the widget can use at all. Called while the dialog is being
        built, so it can only depend on what the subclass arranged before calling the constructor.
        """
        return False

    def setup(self) -> None:
        """
        What the subclass does with the widgets once all of them are there.

        Reach them through :meth:`widget` and :meth:`widgets_of`, e.g. to offer the settings of one
        section only while they mean something.
        """
        pass