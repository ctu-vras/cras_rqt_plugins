# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable service and appearance of the button plugins."""

from dataclasses import dataclass, field

from cras_rqt_common.color import to_color, to_optional_color
from cras_rqt_common.settings import SettingsBase


def _service(label: str, description: str) -> dict:
    """Metadata of a setting with a service name."""
    return {'label': label, 'description': description, 'section': 'Service'}


def _text(label: str, description: str, allow_empty: bool = False) -> dict:
    """Metadata of a setting with a text shown on the button."""
    return {'label': label, 'description': description, 'section': 'Appearance',
            'allow_empty': allow_empty}


# the value of a color setting asking for the color the Qt style uses for the button
STANDARD = ''


def _color(label: str, description: str, optional: bool = False,
           hold_only: bool = False) -> dict:
    """
    Metadata of a setting with a color of the button.

    :param hold_only: whether the setting only makes sense for a button that is held, so that it
        can be hidden in the configuration dialog of the buttons that are only clicked
    """
    return {'label': label, 'description': description, 'section': 'Appearance', 'kind': 'color',
            'optional': optional, 'hold_only': hold_only}


def _number(label: str, description: str, suffix: str, decimals: int,
            limits: tuple[float, float], step: float, hold_only: bool = False) -> dict:
    """Metadata of a numeric setting."""
    return {'label': label, 'description': description, 'section': 'Behaviour', 'suffix': suffix,
            'decimals': decimals, 'limits': limits, 'step': step, 'hold_only': hold_only}


def _flag(label: str, description: str, hold_only: bool = False) -> dict:
    """
    Metadata of a setting that can be switched on and off.

    :param hold_only: whether the setting only makes sense for a button that is held, so that it
        can be hidden in the configuration dialog of the buttons that are only clicked
    """
    return {'label': label, 'description': description, 'section': 'Behaviour', 'kind': 'bool',
            'hold_only': hold_only}


@dataclass
class ButtonSettings(SettingsBase):
    """
    Everything the button plugins can be told to do differently.

    The metadata of each field drives both the configuration dialog and the command line parsing,
    so a new setting only needs to be added here.
    """

    service_name: str = field(default='trigger', metadata=_service(
        'Service name', 'The name of the std_srvs service the button calls. Relative names are '
        'resolved in the namespace of the plugin.'))
    button_text: str = field(default='Button', metadata=_text('Button text', 'What the button says.', allow_empty=True))
    button_color: str = field(default=STANDARD, metadata=_color(
        'Button color', 'The standard color of the button. Leave it empty '
        'to paint the button the way an ordinary Qt button is painted.', optional=True))
    text_color: str = field(default=STANDARD, metadata=_color(
        'Text color', 'The color of the text on the button. Leave it empty to use the color the '
        'Qt style uses for the text of a button.', optional=True))
    error_color: str = field(default='#ffc62828', metadata=_color(
        'Error color', 'The color of the button once the service call fails. The button stops '
        'being red as soon as it is pressed again.'))
    active_color: str = field(default=STANDARD, metadata=_color(
        'Active color', 'The color of a button that is held once the service accepts that it is '
        'held. Leave it empty to keep the ordinary color of the button.', optional=True,
        hold_only=True))
    active_text_color: str = field(default=STANDARD, metadata=_color(
        'Active text color', 'The color of the text on the button while it is active. Leave it '
        'empty to use the color the Qt style uses for the text of a button.', optional=True,
        hold_only=True))
    response_timeout: float = field(default=10.0, metadata=_number(
        'Response timeout', 'For how long to wait for the response before the call is considered '
        'failed. Use 0 to wait for the response indefinitely.', ' s', 1, (0.0, 600.0), 0.5))
    call_attempts: int = field(default=1, metadata=_number(
        'Call attempts', 'How many times to send the request counting the first try. The request '
        'is sent again until the service accepts it or the attempts are used up, which suits a '
        'service that is only restarting.', '', 0, (1, 10), 1))
    invert_value: bool = field(default=False, metadata=_flag(
        'Invert value', 'Send the opposite value, so false while the button is held and true once '
        'it is released.', hold_only=True))
