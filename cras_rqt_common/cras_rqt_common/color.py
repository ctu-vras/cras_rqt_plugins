# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Color helpers shared by CRAS RQt plugins."""

from python_qt_binding.QtGui import QColor


def to_optional_color(value: QColor | str | None) -> QColor | None:
    """
    Interpret a color value that may also mean no color.

    An empty or invalid value gives ``None`` rather than an arbitrary color.
    """
    if value is None:
        return None
    if isinstance(value, QColor):
        return QColor(value)
    if not isinstance(value, str) or not value.strip():
        return None
    color = QColor(value)
    return color if color.isValid() else None


def to_color(value: QColor | str | None, default: QColor | str | None) -> QColor:
    """Return a valid color, falling back to ``default`` and then gray."""
    color = to_optional_color(value)
    if color is None:
        color = to_optional_color(default)
    return color if color is not None else QColor('gray')
