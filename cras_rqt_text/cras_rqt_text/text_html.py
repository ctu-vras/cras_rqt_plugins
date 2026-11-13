# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Turning the text frame into the rich text the widget shows."""

import re

from python_qt_binding.QtGui import QColor

from cras_rqt_text.text_frame import TextFrame
from cras_rqt_text.text_settings import CENTER, LEFT, RIGHT, STANDARD

ALIGNMENT_CSS = {LEFT: 'left', CENTER: 'center', RIGHT: 'right'}

# An angle bracket that cannot start a tag, such as the one in 3 < 5, is not markup.
STRAY_BRACKET = re.compile('<(?![a-zA-Z/!])')


def css_color(color: QColor) -> str:
    """Write the color as a CSS rgba() value."""
    red, green, blue, alpha = color.red(), color.green(), color.blue(), color.alpha()
    return f'rgba({red}, {green}, {blue}, {alpha / 255:.3f})'


def markup(text: str) -> str:
    """
    Show the text as HTML, keeping the markup the sender put into it.

    Line breaks are kept, so that a plain text with newlines is shown on more lines, and only the
    angle brackets that cannot start a tag are escaped, so that e.g. ``3 < 5`` does not disappear.
    """
    escaped = STRAY_BRACKET.sub('&lt;', text)
    return escaped.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br/>')


def build_html(frame: TextFrame) -> str:
    """
    Write the frame as one HTML block.

    The style goes to a wrapping element, so that any markup the text itself carries wins over it.
    """
    style = ['margin: 0', 'padding: 0', f'font-size: {frame.size_pt:g}pt']
    if frame.color is not None and frame.color != STANDARD:
        # Without a color, the text is shown in whatever color the widget writing it uses.
        style.append(f'color: {css_color(QColor(frame.color))}')
    style.append(f'text-align: {ALIGNMENT_CSS.get(frame.horizontal_alignment, "left")}')
    font = frame.font.strip().strip('\'"')
    if font:
        style.append(f"font-family: '{font}'")
    return f'<div style="{"; ".join(style)}">{markup(frame.text)}</div>'
