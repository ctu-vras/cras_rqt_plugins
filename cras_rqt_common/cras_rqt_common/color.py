# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Color parsing helpers."""

from dataclasses import dataclass
from typing import Sequence

from python_qt_binding.QtGui import QColor


ColorSettingsType = str | tuple[int, int, int] | tuple[int, int, int, int] | tuple[float, float, float] | \
                    tuple[float, float, float, float] | Sequence[int] | Sequence[float]


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: int = 255
    
    def __init__(self, r: 'int | str | QColor | Color', g: int = None, b: int = None, a: int = 255):
        if isinstance(r, Color):
            self.__dict__['r'] = r.r
            self.__dict__['g'] = r.g
            self.__dict__['b'] = r.b
            self.__dict__['a'] = r.a
            return
        if isinstance(r, str):
            r = QColor(r)
        if isinstance(r, QColor):
            self.__dict__['r'] = r.red()
            self.__dict__['g'] = r.green()
            self.__dict__['b'] = r.blue()
            self.__dict__['a'] = r.alpha()
        else:
            assert g is not None
            assert b is not None
            self.__dict__['r'] = r
            self.__dict__['g'] = g
            self.__dict__['b'] = b
            self.__dict__['a'] = a
    
    def red(self) -> int:
        return self.r
    
    def green(self) -> int:
        return self.g
    
    def blue(self) -> int:
        return self.b
    
    def alpha(self) -> int:
        return self.a
    
    def q(self) -> QColor:
        return QColor(self.r, self.g, self.b, self.a)
    
    def lightness(self) -> int:
        return self.q().lightness()
    
    def lighter(self, factor: int) -> 'Color':
        return Color(self.q().lighter(factor))
    
    def darker(self, factor: int) -> 'Color':
        return Color(self.q().darker(factor))
    
    def name(self) -> str:
        return self.q().name()

    def css(self) -> str:
        """The color in a form understood by a Qt style sheet."""
        if self.a == 255:
            return self.name()
        return f'rgba({self.r}, {self.g}, {self.b}, {self.a})'
    

def to_optional_color(value: QColor | Color | ColorSettingsType | None) -> Color | None:
    """
    Interpret a color value that may also mean no color.

    An empty or invalid value gives ``None`` rather than an arbitrary color.
    
    :param value: Color value to interpret.
    :return: Valid color or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, Color):
        return value
    if isinstance(value, QColor):
        return Color(value)
    if isinstance(value, str):
        if not value.strip():
            return None
        color = QColor(value)
    elif isinstance(value, tuple) or isinstance(value, Sequence):
        if len(value) not in (3, 4):
            return None
        if isinstance(value[0], int):
            color = QColor(*value)
        elif isinstance(value[0], float):
            color = QColor(*[int(c * 255) for c in value])
        else:
            try:
                color = QColor(*[int(c) for c in value])
            except Exception:
                return None
    else:
        value = str(value)
        if not value.strip():
            return None
        color = QColor(value)
    return Color(color) if color.isValid() else None


def to_color(value: QColor | ColorSettingsType | None, default: Color | None) -> Color:
    """Return a valid color, falling back to ``default`` and then gray.
    
    :param value: Color value to interpret.
    :param default: Default color value.
    :return: Valid color.
    """
    color = to_optional_color(value)
    if color is None:
        color = to_optional_color(default)
    return color if color is not None else Color('gray')
