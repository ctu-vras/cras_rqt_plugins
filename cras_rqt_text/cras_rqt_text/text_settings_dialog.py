# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Settings dialog of the text plugin."""

from dataclasses import fields

from cras_rqt_text.text_settings import format_color, OVERLAY_TYPE, parse_color, TextSettings
from python_qt_binding.QtGui import QColor
from python_qt_binding.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                                         QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                                         QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                                         QVBoxLayout, QWidget)

try:
    # Qt6
    AllNonFixedFieldsGrow = QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    Ok = QDialogButtonBox.StandardButton.Ok
    Cancel = QDialogButtonBox.StandardButton.Cancel
except AttributeError:
    # Qt5
    AllNonFixedFieldsGrow = QFormLayout.AllNonFixedFieldsGrow
    Ok = QDialogButtonBox.Ok
    Cancel = QDialogButtonBox.Cancel

# What to show as the standard color when nobody says what the standard color of the widget is.
BLACK = (0, 0, 0, 255)


class ColorButton(QWidget):
    """
    A button showing a color, asking for a new one when it is clicked.

    A color does not have to be picked at all, in which case the widget shows the text in the
    colors any other rqt widget uses, and says so on the button.
    """

    def __init__(self, color, standard: tuple = None, parent=None):
        super().__init__(parent)
        self._standard = parse_color(standard, BLACK)
        self._color = parse_color(color, self._standard) if color is not None else None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._swatch = QPushButton(self)
        self._swatch.clicked.connect(self._ask_for_color)
        self._standard_button = QPushButton('Standard', self)
        self._standard_button.clicked.connect(self._use_standard_color)
        layout.addWidget(self._swatch)
        layout.addWidget(self._standard_button)
        self._show_color()

    def color(self):
        """
        Give the color the user picked, or ``None`` for the one rqt uses here.

        The color is given as red, green, blue and alpha from 0 to 255.
        """
        return self._color

    def _ask_for_color(self) -> None:
        color = QColorDialog.getColor(QColor(*self._shown_color()), self, 'Choose a color',
                                      QColorDialog.ShowAlphaChannel)
        if not color.isValid():
            return
        self._color = (color.red(), color.green(), color.blue(), color.alpha())
        self._show_color()

    def _use_standard_color(self) -> None:
        self._color = None
        self._show_color()

    def _shown_color(self) -> tuple:
        return self._color if self._color is not None else self._standard

    def _show_color(self) -> None:
        """Show the chosen color on the button, readable over both light and dark colors."""
        shown = self._shown_color()
        standard = '' if self._color is not None else ' (standard)'
        self._swatch.setText(f'{format_color(shown)}{standard}')
        # Write dark text over a light swatch and light text over a dark one.
        light = sum(shown[:3]) > 3 * 127
        on_top = '#000000' if light else '#ffffff'
        self._swatch.setStyleSheet(
            f'background-color: {format_color(shown[:3])}; color: {on_top};')
        self._standard_button.setEnabled(self._color is not None)
        self._standard_button.setToolTip(
            f'Use the color every other rqt widget has here, {format_color(self._standard)}')


class TextSettingsDialog(QDialog):
    """A dialog asking for the topic, the message type and the text appearance to use."""

    def __init__(self, settings: TextSettings, parent=None, standard_colors: dict = None):
        """
        Show the settings, with the colors of the widget ready for the settings that have none.

        :param standard_colors: the colors of the widget the settings belong to, by setting name,
            to show and to go back to where a setting asks for no color of its own.
        """
        super().__init__(parent)
        self.setWindowTitle('Text configuration')
        self._standard_colors = standard_colors or {}
        self._widgets = {}
        self._overlay_widgets = []
        overlay_label = None

        layout = QVBoxLayout(self)
        sections = {}
        for item in fields(TextSettings):
            sections.setdefault(item.metadata.get('section'), []).append(item)
        for section, items in sections.items():
            if section:
                heading = QLabel(f'<b>{section}</b>')
                layout.addWidget(heading)
                if section == 'OverlayText':
                    overlay_label = heading
            form = QFormLayout()
            form.setFieldGrowthPolicy(AllNonFixedFieldsGrow)
            for item in items:
                widget = self._create_widget(item, getattr(settings, item.name),
                                             self._standard_colors.get(item.name))
                widget.setToolTip(item.metadata.get('description', ''))
                self._widgets[item.name] = widget
                if section == 'OverlayText':
                    self._overlay_widgets.append(widget)
                form.addRow(item.metadata.get('label', item.name), widget)
            layout.addLayout(form)

        self._overlay_widgets.append(overlay_label)
        self._widgets['message_type'].currentIndexChanged.connect(self._show_overlay_settings)
        self._show_overlay_settings()

        buttons = QDialogButtonBox(Ok | Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(420)

    def settings(self) -> TextSettings:
        """Collect the values entered by the user."""
        values = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[name] = widget.currentData()
            elif isinstance(widget, ColorButton):
                values[name] = widget.color()  # None stays None, meaning the standard color
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[name] = widget.value()
            else:
                values[name] = widget.text().strip()
        return TextSettings(**values)

    def _create_widget(self, item, value, standard=None):
        metadata = item.metadata
        kind = metadata['kind']
        if kind == 'flag':
            widget = QCheckBox(self)
            widget.setChecked(bool(value))
            return widget
        if kind == 'choice':
            widget = QComboBox(self)
            widget.setEditable(False)
            for option, option_label in metadata['options']:
                widget.addItem(option_label, option)
            index = widget.findData(value)
            widget.setCurrentIndex(index if index >= 0 else 0)
            return widget
        if kind == 'color':
            return ColorButton(value, standard, self)
        if kind == 'number':
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

    def _show_overlay_settings(self) -> None:
        """Offer what the OverlayText messages can be told to do only while there are some."""
        overlay = self._widgets['message_type'].currentData() == OVERLAY_TYPE
        for widget in self._overlay_widgets:
            widget.setEnabled(overlay)
