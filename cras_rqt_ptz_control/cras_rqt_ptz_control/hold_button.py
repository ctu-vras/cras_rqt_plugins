# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""A push button that tells a short tap apart from a long press."""

from python_qt_binding.QtCore import QEvent, QObject, Qt, QTimer, Signal
from python_qt_binding.QtWidgets import QPushButton

TOUCH_EVENTS = (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd, QEvent.TouchCancel)


def _event_point(source):
    """Extract a QPoint out of a mouse or touch point of either Qt 5 or Qt 6 bindings."""
    for name in ('position', 'pos'):
        getter = getattr(source, name, None)
        if callable(getter):
            try:
                point = getter()
            except TypeError:
                continue
            return point.toPoint() if hasattr(point, 'toPoint') else point
    return None


class HoldButton(QPushButton):
    """
    A push button reacting both to a quick tap and to a long press.

    A tap, i.e. a press released sooner than :meth:`set_hold_delay` allows, emits :attr:`tapped`.
    A long press emits :attr:`hold_started` and, once the button is released again,
    :attr:`hold_finished`. Mouse and touch input are both handled; accepting a touch event also
    keeps Qt from synthesizing a mouse click for it.
    """

    tapped = Signal()
    hold_started = Signal()
    hold_finished = Signal()

    def __init__(self, text: str = '', parent: QObject = None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        self._hold_delay = 250
        self._pressed = False
        self._holding = False
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._start_holding)

    def set_hold_delay(self, msec: int) -> None:
        """Set how long the button has to be pressed to be considered held."""
        self._hold_delay = max(0, int(msec))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._begin_press()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = _event_point(event)
            self._end_press(point is None or self.rect().contains(point))
        super().mouseReleaseEvent(event)

    def touchEvent(self, event):
        if event.type() not in TOUCH_EVENTS:
            super().touchEvent(event)
            return
        point = _event_point(event.lastPoint()) if hasattr(event, 'lastPoint') else None
        inside = point is None or self.rect().contains(point)
        if event.type() == QEvent.TouchBegin:
            self._begin_press()
        elif event.type() == QEvent.TouchUpdate:
            if not inside:
                self._end_press(False)
        else:
            self._end_press(inside and event.type() == QEvent.TouchEnd)
        event.accept()

    def _begin_press(self) -> None:
        if self._pressed:
            return
        self._pressed = True
        self.setDown(True)
        self._hold_timer.start(self._hold_delay)

    def _start_holding(self) -> None:
        if not self._pressed or self._holding:
            return
        self._holding = True
        self.hold_started.emit()

    def _end_press(self, inside: bool) -> None:
        if not self._pressed:
            return
        self._hold_timer.stop()
        tapped = inside and not self._holding
        holding = self._holding
        self._pressed = False
        self._holding = False
        self.setDown(False)
        if tapped:
            self.tapped.emit()
        elif holding:
            self.hold_finished.emit()
