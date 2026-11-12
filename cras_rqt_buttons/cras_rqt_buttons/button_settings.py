# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable service and appearance of the button plugins."""

import argparse
from dataclasses import dataclass, field, fields, replace
from typing import Any, Optional, Sequence, Set, Tuple

from python_qt_binding.QtGui import QColor


def _service(label: str, description: str) -> dict:
    """Metadata of a setting with a service name."""
    return {'label': label, 'description': description, 'section': 'Service'}


def _text(label: str, description: str, allow_empty: bool = False) -> dict:
    """Metadata of a setting with a text shown on the button."""
    return {'label': label, 'description': description, 'section': 'Appearance',
            'allow_empty': allow_empty}


#: the value of a color setting asking for the color the Qt style uses for the button
STANDARD = ''


def _color(label: str, description: str, optional: bool = False) -> dict:
    """Metadata of a setting with a color of the button."""
    return {'label': label, 'description': description, 'section': 'Appearance', 'kind': 'color',
            'optional': optional}


def _number(label: str, description: str, suffix: str, decimals: int,
            limits: Tuple[float, float], step: float) -> dict:
    """Metadata of a numeric setting."""
    return {'label': label, 'description': description, 'section': 'Behaviour', 'suffix': suffix,
            'decimals': decimals, 'limits': limits, 'step': step}


def _flag(label: str, description: str, hold_only: bool = False) -> dict:
    """
    Metadata of a setting that can be switched on and off.

    :param hold_only: whether the setting only makes sense for a button that is held, so that it
        can be hidden in the configuration dialog of the buttons that are only clicked
    """
    return {'label': label, 'description': description, 'section': 'Behaviour', 'kind': 'bool',
            'hold_only': hold_only}


def to_optional_color(value: Any) -> Optional[QColor]:
    """
    Interpret the given value as a color that the button may also not have at all.

    An empty value stands for ``None``, which means that the button is painted the way an ordinary
    Qt button is, and anything that cannot be understood is treated the same way rather than
    making the button end up in a color nobody asked for.
    """
    if value is None:
        return None
    if isinstance(value, QColor):
        return QColor(value)
    if not isinstance(value, str) or not value.strip():
        return None
    color = QColor(value)
    return color if color.isValid() else None


def to_color(value: Any, default: Any) -> QColor:
    """
    Interpret the given value as a color.

    Anything :class:`QColor` understands is accepted (names such as ``red``, hex strings such as
    ``#4a90d9``, and colors themselves). Anything that cannot be understood is replaced by
    ``default``, which is interpreted the same way.
    """
    color = QColor(value) if isinstance(value, (str, QColor)) else QColor()
    if not color.isValid():
        color = QColor(default) if isinstance(default, (str, QColor)) else QColor('gray')
    if not color.isValid():
        color = QColor('gray')
    return color


def _to_text(value: Any, default: str, allow_empty: bool = False) -> str:
    if value is None:
        return default
    text = str(value)
    if not text.strip() and not allow_empty:
        return default
    return text


TRUE_WORDS = ('1', 'true', 'yes', 'on')
FALSE_WORDS = ('0', 'false', 'no', 'off')


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        # rqt keeps the settings as text, so this is the way a bool comes back from a perspective
        if text in TRUE_WORDS:
            return True
        if text in FALSE_WORDS:
            return False
    return default


def _to_number(value: Any, default, limits: Tuple[float, float], cast):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return default
    return cast(min(max(number, limits[0]), limits[1]))


def _parse(item, value: Any, default: Any) -> Any:
    """
    Interpret the value stored or given for the given setting.

    :param item: the field of :class:`ButtonSettings` the value belongs to, its metadata says how
        the value is to be understood
    :param value: what was stored in the settings, typed on the command line or picked in a dialog
    :param default: the value to fall back to when the given one cannot be used
    """
    metadata = item.metadata
    if item.type is bool:
        return _to_bool(value, default)
    if item.type is float:
        return _to_number(value, default, metadata['limits'], float)
    if item.type is int:
        return _to_number(value, default, metadata['limits'], int)
    if metadata.get('kind') == 'color':
        if not metadata.get('optional'):
            return to_color(value, default).name()
        if value is None or (isinstance(value, str) and not value.strip()):
            return STANDARD  # no color of its own, so the Qt style decides how the button looks
        color = to_optional_color(value)
        return color.name() if color is not None else default
    return _to_text(value, default, metadata.get('allow_empty', False))


@dataclass
class ButtonSettings:
    """
    Everything the button plugins can be told to do differently.

    The metadata of each field drives both the configuration dialog and the command line parsing,
    so a new setting only needs to be added here.
    """

    service_name: str = field(default='trigger', metadata=_service(
        'Service name', 'The name of the std_srvs service the button calls. Relative names are '
        'resolved in the namespace of the plugin.'))
    button_text: str = field(default='Button', metadata=_text(
        'Button text', 'What the button says. The text is made as large as the button is.',
        allow_empty=True))
    button_color: str = field(default=STANDARD, metadata=_color(
        'Button color', 'The color of the button while it is ready to be pressed. Leave it empty '
        'to paint the button the way an ordinary Qt button is painted.', optional=True))
    text_color: str = field(default=STANDARD, metadata=_color(
        'Text color', 'The color of the text on the button. Leave it empty to use the color the '
        'Qt style uses for the text of a button.', optional=True))
    error_color: str = field(default='#c62828', metadata=_color(
        'Error color', 'The color of the button once the service call fails. The button stops '
        'being red as soon as it is pressed again.'))
    response_timeout: float = field(default=10.0, metadata=_number(
        'Response timeout', 'For how long to wait for the response before the call is considered '
        'failed. Use 0 to wait for the response indefinitely.', ' s', 1, (0.0, 600.0), 0.5))
    invert_value: bool = field(default=False, metadata=_flag(
        'Invert value', 'Send the opposite value, so false while the button is held and true once '
        'it is released.', hold_only=True))

    def save(self, settings) -> None:
        """Store all values in the given rqt settings proxy."""
        for item in fields(self):
            settings.set_value(item.name, getattr(self, item.name))

    @classmethod
    def load(cls, settings, defaults: Optional['ButtonSettings'] = None) -> 'ButtonSettings':
        """
        Load all values from the given rqt settings proxy.

        Unknown, empty or malformed values are silently replaced by the values of ``defaults``
        (or by the built-in defaults when they are not given).
        """
        base = cls() if defaults is None else defaults
        values = {}
        for item in fields(cls):
            default = getattr(base, item.name)
            raw = settings.value(item.name, default)
            values[item.name] = _parse(item, raw, default)
        return cls(**values)

    @classmethod
    def arg_parser(cls) -> argparse.ArgumentParser:
        """A parser accepting all the settings as ``--field_name value`` options."""
        parser = argparse.ArgumentParser(add_help=False)
        cls.add_arguments(parser)
        return parser

    @classmethod
    def add_arguments(cls, parser) -> None:
        """
        Offer all the settings as ``--field_name value`` options on the given parser.

        RQt uses this when a plugin is started on its own, so that it knows which options belong
        to the plugin and passes them to it.
        """
        for item in fields(cls):
            metadata = item.metadata
            options = [f'--{item.name}', f'--{item.name.replace("_", "-")}']
            if item.type is bool:
                # the value may be left out, so that --invert_value alone switches it on
                parser.add_argument(*options, dest=item.name, nargs='?', const=True,
                                    metavar='BOOL', help=metadata.get('description', ''))
            elif item.type in (float, int):
                parser.add_argument(*options, dest=item.name, type=float, metavar='NUMBER',
                                    help=metadata.get('description', ''))
            else:
                metavar = 'COLOR' if metadata.get('kind') == 'color' else 'TEXT'
                parser.add_argument(*options, dest=item.name, metavar=metavar,
                                    help=metadata.get('description', ''))

    @classmethod
    def from_args(cls, argv: Sequence[str], defaults: Optional['ButtonSettings'] = None
                  ) -> Tuple['ButtonSettings', Set[str]]:
        """
        Read the settings given on the command line.

        :param argv: arguments to parse, anything that is not a setting is ignored
        :param defaults: values to use for the settings that are not given
        :returns: the settings and the names of the settings the caller actually gave
        """
        parsed, _ = cls.arg_parser().parse_known_args(list(argv))
        base = cls() if defaults is None else defaults
        values = {}
        given = set()
        for item in fields(cls):
            raw = getattr(parsed, item.name)
            if raw is None:
                continue
            default = getattr(base, item.name)
            values[item.name] = _parse(item, raw, default)
            given.add(item.name)
        return replace(base, **values), given
