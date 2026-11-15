# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable topic, message type and text appearance of the text plugin."""

from dataclasses import dataclass

from python_qt_binding.QtWidgets import QWidget

from cras_rqt_common.color import Color
from cras_rqt_common.settings import SettingsBase
from cras_rqt_common.settings_dialog import SettingsDialog
from cras_rqt_common.settings_fields import BoolField, ChoiceField, FloatField, IntField, OptionalColorField, TextField

STRING_TYPE = 'std_msgs/msg/String'
OVERLAY_TYPE = 'rviz_2d_overlay_msgs/msg/OverlayText'

# The alignment values are the constants of rviz_2d_overlay_msgs/msg/OverlayText.
LEFT = 0
RIGHT = 1
CENTER = 2
TOP = 3
BOTTOM = 4

TYPE_OPTIONS = (
    (STRING_TYPE, 'std_msgs/String'),
    (OVERLAY_TYPE, 'rviz_2d_overlay_msgs/OverlayText')
)
HORIZONTAL_OPTIONS = ((LEFT, 'Left'), (CENTER, 'Center'), (RIGHT, 'Right'))
VERTICAL_OPTIONS = ((TOP, 'Top'), (CENTER, 'Center'), (BOTTOM, 'Bottom'))

SEC_TOPIC = 'Topic'
SEC_TEXT = 'Text'
SEC_OVERLAY = 'OverlayText'


@dataclass
class TextSettings(SettingsBase):
    """Everything the text plugin can be told to do differently."""

    topic: str = TextField(  # type: ignore[bad-assignment]
        'overlay_text', 'Topic',
        'The topic the text is coming from. Leave empty to only show the default text.', SEC_TOPIC)
    message_type: str = ChoiceField(  # type: ignore[bad-assignment]
        STRING_TYPE, 'Message type',
        'Whether the topic carries std_msgs/String or rviz_2d_overlay_msgs/OverlayText messages. '
        'The OverlayText messages bring their own colors, font, size and position with them.',
        SEC_TOPIC, TYPE_OPTIONS)

    default_text: str = TextField(  # type: ignore[bad-assignment]
        'Waiting for text', 'Default text',
        'What to show until the first message arrives. Markup is interpreted, use <br/> for a line break.', SEC_TEXT)
    text_size_pt: float = FloatField(  # type: ignore[bad-assignment]
        18.0, 'Text size',
        'How tall the text is. OverlayText messages can bring their own size.', SEC_TEXT,
        limits=(1.0, 300.0), suffix=' pt', decimals=1)
    scale_with_widget: bool = BoolField(  # type: ignore[bad-assignment]
        False, 'Scale with widget size',
        'Grow and shrink the text with the widget instead of keeping the text size fixed. The text '
        'size setting then holds for the reference height.', SEC_TEXT)
    reference_height: int = IntField(  # type: ignore[bad-assignment]
        200, 'Reference height',
        'Widget height the text size setting holds for when the text scales with the widget '
        'size.', SEC_TEXT, limits=(10, 10000), step=10, suffix=' px')
    text_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Text color',
        'Color of the text. Leave it unset to use the color rqt writes its own text with. Markup '
        'in the text can override the color either way.', SEC_TEXT)
    background_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Background color',
        'Color the whole widget is filled with before the text is drawn. Leave it unset to use the '
        'background of any other rqt widget, and set it fully transparent to show the text over '
        'whatever is behind the widget.', SEC_TEXT)
    horizontal_alignment: int = ChoiceField(  # type: ignore[bad-assignment]
        LEFT, 'Horizontal alignment', 'Where the text is in the widget horizontally.', SEC_TEXT, HORIZONTAL_OPTIONS)
    vertical_alignment: int = ChoiceField(  # type: ignore[bad-assignment]
        TOP, 'Vertical alignment', 'Where the text is in the widget vertically.', SEC_TEXT, VERTICAL_OPTIONS)

    take_style_from_message: bool = BoolField(  # type: ignore[bad-assignment]
        True, 'Use size, font and color from the message',
        'Show the OverlayText messages with the size, font and color they carry. When unticked, '
        'the colors and the text size configured above are used instead.', SEC_OVERLAY)
    take_background_from_message: bool = BoolField(  # type: ignore[bad-assignment]
        True, 'Use background color from the message',
        'Show the OverlayText messages over the background color they carry. When unticked, the '
        'background color configured above is used instead.', SEC_OVERLAY)
    take_layout_from_message: bool = BoolField(  # type: ignore[bad-assignment]
        True, 'Use position from the message',
        'Show the OverlayText messages where they ask for, using the alignment, distances and size '
        'they carry. When unticked, the alignment configured above is used instead.', SEC_OVERLAY)

    @property
    def overlay_messages(self) -> bool:
        """Tell whether the topic carries OverlayText rather than plain String messages."""
        return self.message_type == OVERLAY_TYPE


class TextSettingsDialog(SettingsDialog[TextSettings]):
    """
    A dialog asking for the topic, the message type and the text appearance to use.

    What the OverlayText messages can be told to do is only offered while the widget is set up to
    listen to them, because no message is going to tell the widget anything else.
    """
    def __init__(self, settings: TextSettings, title: str = 'Text Configuration', parent: QWidget = None):
        super().__init__(settings, title, parent)

    def setup(self) -> None:
        self.widget('message_type').currentIndexChanged.connect(self._show_overlay_settings)
        self._show_overlay_settings()

    def _show_overlay_settings(self) -> None:
        """Offer what the OverlayText messages can be told to do only while there are some."""
        overlay = self.widget('message_type').currentData() == OVERLAY_TYPE
        for widget in self.widgets_of(SEC_OVERLAY).values():
            widget.setEnabled(overlay)
