# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The GUI of the text plugin."""

from typing import Dict, Optional, Tuple

from cras_rqt_text.text_engine import TextEngine
from cras_rqt_text.text_frame import build_frame
from cras_rqt_text.text_html import build_html
from cras_rqt_text.text_settings import BOTTOM, RIGHT, TextSettings, TOP
from cras_rqt_text.text_settings_dialog import TextSettingsDialog
from python_qt_binding.QtCore import QSize
from python_qt_binding.QtGui import QColor, QPainter, QPalette, QTextDocument
from python_qt_binding.QtWidgets import QDialog, QSizePolicy, QWidget


class TextWidget(QWidget):
    """
    A widget showing a text coming from a ROS topic.

    The text is shown as rich text, so the markup the sender put into it is interpreted, and the
    widget fills the space it is given, with the text sitting in it where the settings or the
    messages ask for. Until the first message arrives, the configured default text is shown.

    The colors the settings do not ask for are the ones any other rqt widget uses, so that the
    plugin looks like the rest of rqt until it is told to look like anything else.
    """

    DEFAULT_WIDTH = 300  # px, what to ask for when the messages do not say otherwise
    DEFAULT_HEIGHT = 120

    def __init__(self, node, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName('cras_rqt_text__Text')
        self.setWindowTitle('Text')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._settings = TextSettings()
        self._message = None
        self._preferred_size = None
        self._cached_document = None
        self._cached_html = None
        self._engine = TextEngine(node, self)
        self._engine.string_text.connect(self._show)
        self._engine.overlay_text.connect(self._show)

    def open_configuration(self) -> None:
        """Let the user change the topic, the message type and the text appearance."""
        dialog = TextSettingsDialog(self._settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings = dialog.settings()
        self._apply_settings()

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Store the settings in the rqt settings."""
        self._settings.save(instance_settings)

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Load the settings from the rqt settings and use them right away."""
        self._settings = TextSettings.load(instance_settings)
        self._apply_settings()

    def shutdown(self) -> None:
        """Release the ROS interfaces."""
        self._engine.shutdown()

    def sizeHint(self) -> QSize:
        """Ask for the size the last message wanted, so that the text has room for what it says."""
        if self._preferred_size is not None:
            return self._preferred_size
        return QSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

    def paintEvent(self, event):
        frame = self._frame()
        painter = QPainter(self)
        if frame is None:
            painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
            return
        background = QColor(frame.background) if frame.background else self.palette().color(QPalette.ColorRole.Window)
        if background.alpha() < 255:
            # Paint the plain widget background first, so that a translucent background does not
            # leave anything of the text shown before behind.
            painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
        painter.fillRect(self.rect(), background)
        if not frame.text.strip():
            return
        document = self._document_for(build_html(frame))
        document.setTextWidth(max(self.width(), 1))
        painter.translate(self._offset_x(frame), self._offset_y(frame, document.size().height()))
        document.drawContents(painter)

    def _show(self, message) -> None:
        self._message = message
        self._redraw()

    def _apply_settings(self) -> None:
        self._engine.configure(self._settings)
        self._redraw()

    def _redraw(self) -> None:
        """Show the current message, asking for the room it wants if it wants any different."""
        preferred = self._preferred_size_of(self._frame())
        if preferred != self._preferred_size:
            self._preferred_size = preferred
            self.updateGeometry()
        self.update()

    def _frame(self):
        return build_frame(self._settings, self._message, self.height())

    @staticmethod
    def _preferred_size_of(frame) -> Optional[QSize]:
        if frame is None or frame.preferred_width <= 0 or frame.preferred_height <= 0:
            return None
        return QSize(frame.preferred_width, frame.preferred_height)

    def _document_for(self, html: str) -> QTextDocument:
        """Build the rich text document of the given HTML, again only when the HTML changed."""
        if self._cached_document is None or self._cached_html != html:
            document = QTextDocument()
            document.setDocumentMargin(0)
            document.setHtml(html)
            self._cached_document = document
            self._cached_html = html
        return self._cached_document

    @staticmethod
    def _offset_x(frame) -> int:
        """How much to move the text to the right; the distance is measured from the border."""
        if frame.horizontal_alignment == RIGHT:
            return -frame.horizontal_distance
        return frame.horizontal_distance

    def _offset_y(self, frame, text_height: float) -> int:
        """How much to move the text down; the distance is measured from the border."""
        free = self.height() - int(text_height)
        if frame.vertical_alignment == TOP:
            return frame.vertical_distance
        if frame.vertical_alignment == BOTTOM:
            return free - frame.vertical_distance
        return int(free / 2) + frame.vertical_distance
