# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""What the button plugins are told to do and how they look."""

from dataclasses import dataclass

from cras_rqt_common.color import Color
from cras_rqt_common.color_widgets import CLEAR_TIP
from cras_rqt_common.settings import SettingsBase
from cras_rqt_common.settings_fields import (
    BoolField, FloatField, IntField, OptionalColorField, RequiredColorField, TextField)

ERROR_COLOR = Color('#c62828')
"""the color of a button whose last service call failed"""

BUTTON_CLEAR_TIP = f'{CLEAR_TIP} The button then looks like any other Qt button.'
"""what the button that takes the color of a button away says"""

SEC_SERVICE = 'Service'
SEC_APPEARANCE = 'Appearance'
SEC_BEHAVIOR = 'Behavior'


@dataclass
class ButtonSettings(SettingsBase):
    """
    Basic settings of all buttons.
    """

    button_text: str = TextField(  # type: ignore[bad-assignment]
        'Button', 'Button text', 'What the button says. The text is made as large as the button is.',
        SEC_APPEARANCE)
    button_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Button color', 'The color the button is painted with. Leave it unset to use the standard look of a '
        'Qt button, and set it fully transparent to only show the frame and the text.', SEC_APPEARANCE,
        clear_tip=BUTTON_CLEAR_TIP)
    text_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Text color', 'The color of the text on the button. Leave it unset to use the color that fits the '
        'color of the button best.', SEC_APPEARANCE)


@dataclass
class ServiceButtonSettings(ButtonSettings):
    """
    The service a button calls, the text it shows and the colors it is painted with.

    These are all the settings of a button connected to a service.
    """

    service_name: str = TextField(  # type: ignore[bad-assignment]
        '', 'Service name', 'The service the button calls when it is used.', SEC_SERVICE, allow_empty=False)
    button_text: str = TextField(  # type: ignore[bad-assignment]
        'Button', 'Button text', 'What the button says. The text is made as large as the button is.',
        SEC_APPEARANCE)
    button_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Button color', 'The color the button is painted with. Leave it unset to use the standard look of a '
        'Qt button, and set it fully transparent to only show the frame and the text.', SEC_APPEARANCE,
        clear_tip=BUTTON_CLEAR_TIP)
    text_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Text color', 'The color of the text on the button. Leave it unset to use the color that fits the '
        'color of the button best.', SEC_APPEARANCE)
    error_color: Color = RequiredColorField(  # type: ignore[bad-assignment]
        ERROR_COLOR, 'Error color', 'The color the button turns when the service refuses the request or does not '
        'answer at all. A failure has to stay visible, so this color cannot be taken away.', SEC_APPEARANCE)

    response_timeout: float = FloatField(  # type: ignore[bad-assignment]
        10.0, 'Response timeout', 'How long to wait for the service to answer before the call is considered lost. '
        'Use 0 to wait for the response indefinitely.', SEC_BEHAVIOR,
        limits=(0.0, 600.0), step=0.5, decimals=1, suffix=' s')
    call_attempts: int = IntField(  # type: ignore[bad-assignment]
        1, 'Call attempts', 'How many times to send the request counting the first try. The request is sent again '
        'until the service accepts it or the attempts are used up, which suits a service that is only restarting.',
        SEC_BEHAVIOR, limits=(1, 10), step=1)


@dataclass
class ClickButtonSettings(ServiceButtonSettings):
    pass


@dataclass
class HoldButtonSettings(ServiceButtonSettings):
    """
    What a button that is held asks for on top of what a button that is only clicked asks for.

    A held button does its work twice: once when the operator presses it, and once when they let go
    of it. That is also the only case when the service is asked to remember something between the two
    calls, and when the button has a color to show that the service accepted the button is held.
    """

    active_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Active color', 'The color the button turns once the service accepts that the button is being held. '
        'Leave it unset to keep the ordinary color of the button.', SEC_APPEARANCE, clear_tip=BUTTON_CLEAR_TIP)
    active_text_color: Color | None = OptionalColorField(  # type: ignore[bad-assignment]
        None, 'Active text color', 'The color of the text while the button is active. Leave it unset to keep the '
        'ordinary color of the text.', SEC_APPEARANCE)
    invert_value: bool = BoolField(  # type: ignore[bad-assignment]
        False, 'Send the opposite value', 'Send the value that is opposite to what the button does by default, i.e. '
        'false while the button is held and true once it is released.', SEC_BEHAVIOR)
