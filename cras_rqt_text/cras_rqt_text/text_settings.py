# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable topic, message type and text appearance of the text plugin."""

from dataclasses import dataclass, field

from cras_rqt_common.color import to_optional_color
from cras_rqt_common.settings import SettingsBase, parse_color

STRING_TYPE = 'std_msgs/msg/String'
OVERLAY_TYPE = 'rviz_2d_overlay_msgs/msg/OverlayText'

# The alignment values are the constants of rviz_2d_overlay_msgs/msg/OverlayText.
LEFT = 0
RIGHT = 1
CENTER = 2
TOP = 3
BOTTOM = 4

TYPE_OPTIONS = ((STRING_TYPE, 'std_msgs/String'),
                (OVERLAY_TYPE, 'rviz_2d_overlay_msgs/OverlayText'))
HORIZONTAL_OPTIONS = ((LEFT, 'Left'), (CENTER, 'Center'), (RIGHT, 'Right'))
VERTICAL_OPTIONS = ((TOP, 'Top'), (CENTER, 'Center'), (BOTTOM, 'Bottom'))

STANDARD = ''


def _setting(label: str, description: str, section: str, kind: str, **extra) -> dict:
    """Describe to the configuration dialog what to ask for."""
    if kind == 'text':
        extra.setdefault('allow_empty', True)
    metadata = {'label': label, 'description': description, 'section': section, 'kind': kind}
    metadata.update(extra)
    return metadata


def _choice(label: str, description: str, section: str, options: tuple) -> dict:
    return _setting(label, description, section, 'choice', options=options)


def _number(label: str, description: str, section: str, suffix: str, decimals: int,
            limits: tuple[float, float], step: float) -> dict:
    return _setting(label, description, section, 'number', suffix=suffix, decimals=decimals,
                    limits=limits, step=step)


def _flag(label: str, description: str, section: str) -> dict:
    return _setting(label, description, section, 'flag')


def _color(label: str, description: str, section: str) -> dict:
    """Describe a color; leaving it unset means the color any other rqt widget uses."""
    return _setting(label, description, section, 'color', optional=True)


@dataclass
class TextSettings(SettingsBase):
    """Everything the text plugin can be told to do differently."""

    topic: str = field(default='overlay_text', metadata=_setting(
        'Topic', 'The topic the text is coming from. Leave empty to only show the default text.',
        'Topic', 'text'))
    message_type: str = field(default=STRING_TYPE, metadata=_choice(
        'Message type', 'Whether the topic carries std_msgs/String or '
        'rviz_2d_overlay_msgs/OverlayText messages. The OverlayText messages bring their own '
        'colors, font, size and position with them.', 'Topic', TYPE_OPTIONS))

    default_text: str = field(default='Waiting for text', metadata=_setting(
        'Default text', 'What to show until the first message arrives. Markup is interpreted, '
        'use <br/> for a line break.', 'Text', 'text'))
    text_size_pt: float = field(default=18.0, metadata=_number(
        'Text size', 'How tall the text is. OverlayText messages can bring their own size.',
        'Text', ' pt', 1, (1.0, 300.0), 1.0))
    scale_with_widget: bool = field(default=False, metadata=_flag(
        'Scale with widget size', 'Grow and shrink the text with the widget instead of keeping '
        'the text size fixed. The text size setting then holds for the reference height.', 'Text'))
    reference_height: int = field(default=200, metadata=_number(
        'Reference height', 'Widget height the text size setting holds for when the text scales '
        'with the widget size.', 'Text', ' px', 0, (10, 10000), 10))
    text_color: str = field(default=STANDARD, metadata=_color(
        'Text color', 'Color of the text. Leave it unset to use the color rqt writes its own '
        'text with. Markup in the text can override the color either way.', 'Text'))
    background_color: str = field(default=STANDARD, metadata=_color(
        'Background color', 'Color the whole widget is filled with before the text is drawn. '
        'Leave it unset to use the background of any other rqt widget, and set it fully '
        'transparent to show the text over whatever is behind the widget.', 'Text'))
    horizontal_alignment: int = field(default=LEFT, metadata=_choice(
        'Horizontal alignment', 'Where the text is in the widget horizontally.', 'Text',
        HORIZONTAL_OPTIONS))
    vertical_alignment: int = field(default=TOP, metadata=_choice(
        'Vertical alignment', 'Where the text is in the widget vertically.', 'Text',
        VERTICAL_OPTIONS))

    take_style_from_message: bool = field(default=True, metadata=_flag(
        'Use size, font and color from the message',
        'Show the OverlayText messages with the size, font and color they carry. When unticked, '
        'the colors and the text size configured above are used instead.', 'OverlayText'))
    take_background_from_message: bool = field(default=True, metadata=_flag(
        'Use background color from the message',
        'Show the OverlayText messages over the background color they carry. When unticked, the '
        'background color configured above is used instead.', 'OverlayText'))
    take_layout_from_message: bool = field(default=True, metadata=_flag(
        'Use position from the message',
        'Show the OverlayText messages where they ask for, using the alignment, distances and '
        'size they carry. When unticked, the alignment configured above is used instead.',
        'OverlayText'))

    @property
    def overlay_messages(self) -> bool:
        """Tell whether the topic carries OverlayText rather than plain String messages."""
        return self.message_type == OVERLAY_TYPE
