# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Widgets that let the user say which color a plugin should use."""

from python_qt_binding.QtCore import QRectF, QSize, Qt, Signal, Slot
from python_qt_binding.QtGui import QBrush, QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from python_qt_binding.QtWidgets import (QColorDialog, QHBoxLayout, QPushButton, QStyle,
                                         QToolButton, QWidget)

COLOR_BUTTON_WIDTH = 130  # px, wide enough to be a comfortable target for a finger
CHIP_WIDTH = 40  # px, the chip of the color the color selection shows
CHIP_HEIGHT = 18  # px
CHIP_GAP = 8  # px, the space between the chip and the color written next to it
CHIP_CORNER = 3  # px
CLEAR_BUTTON_WIDTH = 34  # px
# what the color selection says while the button is painted the way an ordinary Qt button is
STANDARD_LABEL = 'Standard'
# what the button that takes the color away says; a plugin that knows what happens without the
# color says it its own way
CLEAR_TIP = 'Use a default color.'
# only used when the Qt style has no icon to clear with, which is not expected to happen
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


def color_chip(color: QColor | None, parent: QWidget = None) -> QIcon:
    """
    Paint a chip with the given color.

    :param color: the color of the chip, ``None`` for a chip that stands for the color an ordinary
        Qt button is painted with
    :param parent: the widget whose colors are used to paint the empty chip
    """
    pixmap = QPixmap(CHIP_WIDTH + CHIP_GAP, CHIP_HEIGHT)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    area = QRectF(0.5, 0.5, CHIP_WIDTH - 1.0, CHIP_HEIGHT - 1.0)
    if color is None:
        # a dashed outline, the way a line edit shows it holds nothing
        palette = parent.palette() if parent is not None else QPalette()
        painter.setBrush(palette.brush(QPalette.ColorRole.Button))
        pen = QPen(palette.color(QPalette.ColorRole.Text))
        pen.setStyle(Qt.PenStyle.DashLine)
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

    No color at all is one of the colors to choose, and it means that the widget falls back to the
    color it uses when it is told nothing.
    """

    # the color that is shown now, whenever it changes
    color_changed = Signal(object)

    def __init__(self, color: QColor | None, parent: QWidget = None):
        super().__init__(parent)
        self._color = color
        self.setMinimumWidth(COLOR_BUTTON_WIDTH)
        # the style would otherwise shrink the chip to its idea of an icon
        self.setIconSize(QSize(CHIP_WIDTH + CHIP_GAP, CHIP_HEIGHT))
        self.clicked.connect(self._pick_color)
        self._show_color()

    def color(self) -> QColor | None:
        """Return the color shown, ``None`` for the color to fall back to."""
        return self._color

    def set_color(self, color: QColor | str | None) -> None:
        """Show the given color; ``None`` stands for the color to fall back to."""
        if isinstance(color, str):
            color = QColor(color)
        self._color = color
        self._show_color()
        self.color_changed.emit(self.color())

    @Slot()
    def _pick_color(self) -> None:
        current = self._color if self._color is not None else QColor('gray')
        # the chooser is opened over the dialog it belongs to rather than over this button, so that
        # it cannot end up looking like the color field it was opened from
        chosen = QColorDialog.getColor(current, self.window(), 'Choose color')
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
    A color to pick, with a button that clears it back to the color the widget falls back to.

    The color is shown as a chip of the color itself, so that the field cannot be mistaken for the
    widget next to it. The button that clears the color has nothing to do while there is no color to
    clear away, so it waits disabled until there is one.
    """

    def __init__(self, color: QColor | None, parent: QWidget = None, clear_tip: str = CLEAR_TIP):
        super().__init__(parent)
        self._button = ColorButton(color, self)
        self._button.color_changed.connect(self._color_shown)
        self._clear = QToolButton(self)
        self._clear.setToolTip(clear_tip)
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

    def color(self) -> QColor | None:
        """Return the color shown, ``None`` for the color to fall back to."""
        return self._button.color()

    def set_color(self, color: QColor | None) -> None:
        """Show the given color; ``None`` stands for the color to fall back to."""
        self._button.set_color(color)

    def setToolTip(self, tip: str | None) -> None:
        # the two buttons fill the whole editor, so a tip that only the editor itself knows would
        # be nearly impossible to bring up
        super().setToolTip(tip)
        self._button.setToolTip(tip)

    @Slot(object)
    def _color_shown(self, color: QColor | None) -> None:
        # there is something to clear only while the button has a color of its own, and that also
        # counts for a color picked in the chooser, which never goes through set_color
        self._clear.setEnabled(color is not None)

    @Slot()
    def _use_standard(self) -> None:
        self.set_color(None)
