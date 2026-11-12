# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configuration dialog of the button plugins."""

from dataclasses import fields, replace

from cras_rqt_buttons.button_settings import ButtonSettings, STANDARD, to_optional_color
from python_qt_binding.QtCore import QRectF, QSize, Qt, Signal, Slot
from python_qt_binding.QtGui import QBrush, QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from python_qt_binding.QtWidgets import (QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
                                         QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                                         QLineEdit, QPushButton, QStyle, QToolButton,
                                         QVBoxLayout, QWidget)

try:
    # Qt6
    AllNonFixedFieldsGrow = QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
except AttributeError:
    # broken Qt5
    AllNonFixedFieldsGrow = QFormLayout.AllNonFixedFieldsGrow
    

COLOR_BUTTON_WIDTH = 130  # px, wide enough to be a comfortable target for a finger
CHIP_WIDTH = 40  # px, the chip of the color the color selection shows
CHIP_HEIGHT = 18  # px
CHIP_GAP = 8  # px, the space between the chip and the color written next to it
CHIP_CORNER = 3  # px
CLEAR_BUTTON_WIDTH = 34  # px
#: what the color selection says while the button is painted the way an ordinary Qt button is
STANDARD_LABEL = 'Standard'
CLEAR_TIP = 'Take this color away, so the button is painted the way an ordinary Qt button is.'
#: only used when the Qt style has no icon to clear with, which is not expected to happen
CLEAR_FALLBACK_TEXT = '×'


def clear_icon(style) -> QIcon:
    """
    Return the icon of a button that clears something.

    This is the icon a line edit clears itself with, so that clearing the color is understood the
    same way as clearing a field next to it.
    """
    if hasattr(QStyle, 'SP_LineEditClearButton'):
        icon = style.standardIcon(QStyle.SP_LineEditClearButton)
        if not icon.isNull():
            return icon
    return QIcon.fromTheme('edit-clear')


def color_chip(color, parent: QWidget = None) -> QIcon:
    """
    Paint a chip with the given color, so that the color one picks is impossible to miss.

    :param color: the color of the chip, ``None`` for a chip that stands for the color an ordinary
        Qt button is painted with
    :param parent: the widget whose colors are used to paint the empty chip
    """
    pixmap = QPixmap(CHIP_WIDTH + CHIP_GAP, CHIP_HEIGHT)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    area = QRectF(0.5, 0.5, CHIP_WIDTH - 1.0, CHIP_HEIGHT - 1.0)
    if color is None:
        # a dashed outline, the way a line edit shows it holds nothing
        palette = parent.palette() if parent is not None else QPalette()
        painter.setBrush(palette.brush(QPalette.Button))
        pen = QPen(palette.color(QPalette.Text))
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
    else:
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(150)))
    painter.drawRoundedRect(area, CHIP_CORNER, CHIP_CORNER)
    painter.end()
    return QIcon(pixmap)


class ColorButton(QPushButton):
    """
    A button that shows the color it holds as a chip of that color and opens a color chooser.

    No color at all is one of the colors to choose, and it means that the button is painted the way
    an ordinary Qt button is.
    """

    #: the color that is shown now, whenever it changes; empty for an ordinary Qt button
    color_changed = Signal(str)

    def __init__(self, color, parent: QWidget = None):
        super().__init__(parent)
        self._color = to_optional_color(color)
        self.setMinimumWidth(COLOR_BUTTON_WIDTH)
        # the style would otherwise shrink the chip to its idea of an icon
        self.setIconSize(QSize(CHIP_WIDTH + CHIP_GAP, CHIP_HEIGHT))
        self.clicked.connect(self._pick_color)
        self._show_color()

    def color(self) -> str:
        """Return the color as a hex string, empty for an ordinary Qt button."""
        return STANDARD if self._color is None else self._color.name()

    def set_color(self, color) -> None:
        """Show the given color; an empty one stands for the color of an ordinary Qt button."""
        self._color = to_optional_color(color)
        self._show_color()
        self.color_changed.emit(self.color())

    @Slot()
    def _pick_color(self) -> None:
        current = self._color if self._color is not None else QColor('gray')
        # the chooser is opened over the dialog it belongs to rather than over this button, so that
        # it cannot end up looking like the color field it was opened from
        chosen = QColorDialog.getColor(current, self.window(), 'Choose the color')
        if chosen.isValid():
            self.set_color(chosen)

    def _show_color(self) -> None:
        # The button is left the way the Qt style paints it on purpose: a style sheet set on a
        # widget reaches everything inside it, and that would include the color chooser opened
        # from it. Only the chip of the color is painted, and that is an image, not a widget.
        self.setIcon(color_chip(self._color, self))
        self.setText(STANDARD_LABEL if self._color is None else self._color.name())


class ColorEditor(QWidget):
    """
    A color to pick, with a button that clears it back to an ordinary Qt button.

    The color is shown as a chip of the color itself, so that the field cannot be mistaken for the
    button next to it. The button that clears the color has nothing to do while the button already
    has the standard look, so it waits disabled until there is a color to clear away.
    """

    def __init__(self, color, parent: QWidget = None):
        super().__init__(parent)
        self._button = ColorButton(color, self)
        self._button.color_changed.connect(self._color_shown)
        self._clear = QToolButton(self)
        self._clear.setToolTip(CLEAR_TIP)
        self._clear.setMinimumWidth(CLEAR_BUTTON_WIDTH)
        icon = clear_icon(self.style())
        if icon.isNull():
            self._clear.setText(CLEAR_FALLBACK_TEXT)
        else:
            self._clear.setIcon(icon)
        self._clear.clicked.connect(self._use_standard)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)
        layout.addWidget(self._clear)
        self._color_shown(self._button.color())

    def color(self) -> str:
        """Return the color as a hex string, empty for an ordinary Qt button."""
        return self._button.color()

    def set_color(self, color) -> None:
        """Show the given color; an empty one stands for the color of an ordinary Qt button."""
        self._button.set_color(color)

    def setToolTip(self, tip: str) -> None:
        # the two buttons fill the whole editor, so a tip that only the editor itself knows would
        # be nearly impossible to bring up
        super().setToolTip(tip)
        self._button.setToolTip(tip)

    @Slot(str)
    def _color_shown(self, color: str) -> None:
        # there is something to clear only while the button has a color of its own, and that also
        # counts for a color picked in the chooser, which never goes through set_color
        self._clear.setEnabled(color != STANDARD)

    @Slot()
    def _use_standard(self) -> None:
        self.set_color(STANDARD)


class ButtonSettingsDialog(QDialog):
    """A dialog asking for the service the button should call and how it should look."""

    def __init__(self, settings: ButtonSettings, title: str = 'Button configuration', parent=None,
                 hold_mode: bool = False):
        """
        Show the given settings, section by section.

        :param settings: the values to show in the fields
        :param hold_mode: whether the button is held rather than only clicked, which is the only
            case when a setting that tells what value to send makes any sense
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self._settings = settings
        self._widgets = {}

        layout = QVBoxLayout(self)

        sections = {}
        for item in fields(ButtonSettings):
            if item.metadata.get('hold_only') and not hold_mode:
                continue
            sections.setdefault(item.metadata.get('section'), []).append(item)
        for section, items in sections.items():
            if section:
                layout.addWidget(QLabel(f'<b>{section}</b>'))
            form = QFormLayout()
            form.setFieldGrowthPolicy(AllNonFixedFieldsGrow)
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

    def settings(self) -> ButtonSettings:
        """
        Read the values entered by the user.

        The settings the dialog does not ask for, because they do not apply to the button it was
        opened for, keep the value they had when it was opened.
        """
        values = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, (ColorEditor, ColorButton)):
                values[name] = widget.color()
            elif isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, QDoubleSpinBox):
                values[name] = widget.value()
            else:
                values[name] = widget.text().strip()
        return replace(self._settings, **values)

    def _create_widget(self, item, value):
        metadata = item.metadata
        if metadata.get('kind') == 'color':
            if metadata.get('optional'):
                return ColorEditor(value, self)
            return ColorButton(value, self)
        if item.type is bool:
            widget = QCheckBox(self)
            widget.setChecked(bool(value))
            return widget
        if item.type in (int, float):
            limits = metadata['limits']
            widget = QDoubleSpinBox(self)
            widget.setRange(limits[0], limits[1])
            widget.setSingleStep(metadata['step'])
            widget.setSuffix(metadata.get('suffix', ''))
            widget.setDecimals(metadata.get('decimals', 2))
            widget.setValue(value)
            return widget
        widget = QLineEdit(str(value), self)
        widget.setClearButtonEnabled(True)
        return widget
