# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""What the text plugin shows, built from the settings and the message that arrived."""

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from cras_rqt_text.text_settings import LEFT, TextSettings, TOP

# The biggest size an OverlayText message can ask the widget for, in pixels.
MAX_PREFERRED_SIZE = 4096


@dataclass
class TextFrame:
    """
    A single thing to show in the widget, with everything already decided.

    A ``color`` or a ``background`` left as ``None`` asks for the colors any other rqt widget has.
    Those live in the palette of the widget, so only the widget itself can fill them in.
    """

    text: str = ''
    color: Optional[Tuple[int, int, int, int]] = None
    background: Optional[Tuple[int, int, int, int]] = None
    size_pt: float = 12.0
    font: str = ''
    horizontal_alignment: int = LEFT
    vertical_alignment: int = TOP
    horizontal_distance: int = 0
    vertical_distance: int = 0
    preferred_width: int = 0
    preferred_height: int = 0


def scaling_factor(settings: TextSettings, height: int) -> float:
    """How many times bigger the text has to be in a widget of the given height."""
    if not settings.scale_with_widget or height <= 0:
        return 1.0
    return height / max(settings.reference_height, 1)


def _rgba(color) -> Tuple[int, int, int, int]:
    """Count the channels of a std_msgs/ColorRGBA in 0 to 255 instead of 0 to 1."""
    return tuple(max(0, min(255, int(round(channel * 255))))
                 for channel in (color.r, color.g, color.b, color.a))


def build_frame(settings: TextSettings, message: Any, height: int) -> Optional[TextFrame]:
    """
    Build what to show for the given message with the given settings.

    :param message: the text to show, either as a string or as an OverlayText message,
        or ``None`` when nothing has arrived yet.
    :param height: height of the widget the text is going to be shown in, for the scaling.
    :returns: what to show, or ``None`` when the message asked for the text to be hidden.
    """
    scale = scaling_factor(settings, height)
    if message is None or isinstance(message, str):
        return TextFrame(
            text=settings.default_text if message is None else message,
            color=settings.text_color,
            background=settings.background_color,
            size_pt=settings.text_size_pt * scale,
            horizontal_alignment=settings.horizontal_alignment,
            vertical_alignment=settings.vertical_alignment,
        )

    # An OverlayText message brings its own appearance and position along. The settings only say
    # which of them to listen to and which of them to override.
    if message.action == message.DELETE:
        return None
    frame = TextFrame(
        text=message.text,
        color=settings.text_color,
        background=settings.background_color,
        size_pt=settings.text_size_pt * scale,
        horizontal_alignment=settings.horizontal_alignment,
        vertical_alignment=settings.vertical_alignment,
    )
    if settings.take_style_from_message:
        if message.text_size > 0:
            frame.size_pt = message.text_size * scale
        frame.font = message.font
        frame.color = _rgba(message.fg_color)
    if settings.take_background_from_message:
        frame.background = _rgba(message.bg_color)
    if settings.take_layout_from_message:
        frame.horizontal_alignment = message.horizontal_alignment
        frame.vertical_alignment = message.vertical_alignment
        frame.horizontal_distance = message.horizontal_distance
        frame.vertical_distance = message.vertical_distance
        frame.preferred_width = max(0, min(message.width, MAX_PREFERRED_SIZE))
        frame.preferred_height = max(0, min(message.height, MAX_PREFERRED_SIZE))
    return frame
