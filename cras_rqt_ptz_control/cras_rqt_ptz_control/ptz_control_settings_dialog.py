# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Settings dialog of the PTZ control plugin."""

from dataclasses import fields

from cras_rqt_ptz_control.ptz_control_settings import PtzControlSettings
from python_qt_binding.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                                         QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout)


class PtzControlSettingsDialog(QDialog):
    """A dialog asking for the topics and the command amplitudes used by the PTZ control plugin."""

    def __init__(self, settings: PtzControlSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('PTZ control configuration')
        self._widgets = {}

        layout = QVBoxLayout(self)

        sections = {}
        for item in fields(PtzControlSettings):
            sections.setdefault(item.metadata.get('section'), []).append(item)
        for section, items in sections.items():
            if section:
                layout.addWidget(QLabel(f'<b>{section}</b>'))
            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for item in items:
                widget = self._create_widget(item, getattr(settings, item.name))
                widget.setToolTip(item.metadata.get('description', ''))
                self._widgets[item.name] = widget
                form.addRow(item.metadata.get('label', item.name), widget)
            layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(420)

    def settings(self) -> PtzControlSettings:
        """Read the values entered by the user."""
        values = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[name] = widget.value()
            else:
                values[name] = widget.text().strip()
        defaults = PtzControlSettings()
        for name, value in values.items():
            if isinstance(value, str) and not value:
                values[name] = getattr(defaults, name)
        return PtzControlSettings(**values)

    def _create_widget(self, item, value):
        metadata = item.metadata
        if item.type is bool:
            widget = QCheckBox(self)
            widget.setChecked(bool(value))
            return widget
        if item.type in (int, float):
            limits = metadata['limits']
            widget = QSpinBox(self) if item.type is int else QDoubleSpinBox(self)
            widget.setRange(limits[0], limits[1])
            widget.setSingleStep(metadata['step'])
            widget.setSuffix(metadata.get('suffix', ''))
            if item.type is float:
                widget.setDecimals(metadata.get('decimals', 2))
            widget.setValue(value)
            return widget
        widget = QLineEdit(str(value), self)
        widget.setClearButtonEnabled(True)
        return widget
