# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Helpers for dataclass-backed RQt settings."""

import argparse
from dataclasses import fields, replace
from typing import Any, Sequence

from cras_rqt_common.color import to_color, to_optional_color
from python_qt_binding.QtGui import QColor

TRUE_WORDS = ('1', 'true', 'yes', 'on')
FALSE_WORDS = ('0', 'false', 'no', 'off')


def save_settings(settings, proxy) -> None:
    """Store all dataclass values in the given rqt settings proxy."""
    for item in fields(settings):
        proxy.set_value(item.name, getattr(settings, item.name))


def load_settings(settings_type, proxy, defaults=None):
    """Load a settings dataclass using its field metadata."""
    base = settings_type() if defaults is None else defaults
    values = {}
    for item in fields(settings_type):
        default = getattr(base, item.name)
        raw = proxy.value(item.name, default)
        values[item.name] = parse_setting(item, raw, default)
    return settings_type(**values)


def to_number(value, default, limits: tuple[float, float], cast):
    """Parse and clamp a numeric setting, returning its default when it is malformed."""
    try:
        number = cast(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if number != number:
        return default
    return cast(min(max(number, limits[0]), limits[1]))


def to_bool(value: Any, default: bool) -> bool:
    """Parse common textual and numeric boolean representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in TRUE_WORDS:
            return True
        if text in FALSE_WORDS:
            return False
    return default


def parse_color(value: Any, default: str, *, optional: bool = True) -> str:
    """Parse a color setting and return its canonical ARGB string."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if optional:
            return ''
        value = default
    color = to_optional_color(value)
    if color is None:
        if optional and to_optional_color(default) is None:
            return ''
        color = to_color(default, None)
    return color.name(QColor.NameFormat.HexArgb)


def parse_setting(item, value: Any, default: Any) -> Any:
    """Interpret one dataclass setting using its type and field metadata."""
    metadata = item.metadata
    kind = metadata.get('kind')
    if item.type is bool or kind in ('bool', 'flag'):
        return to_bool(value, default)
    if kind == 'choice':
        if value is not None:
            for option, _ in metadata['options']:
                if option == value or str(option) == str(value).strip():
                    return option
        return default
    if kind == 'color':
        return parse_color(value, default, optional=metadata.get('optional', False))
    if item.type in (int, float):
        return to_number(value, default, metadata['limits'], item.type)
    if value is None:
        return default
    text = str(value).strip()
    if not text and not metadata.get('allow_empty', False):
        return default
    return text


class SettingsBase:
    """Common persistence and command-line parsing for settings dataclasses."""

    def save(self, proxy) -> None:
        save_settings(self, proxy)

    @classmethod
    def load(cls, proxy, defaults=None):
        return load_settings(cls, proxy, defaults)

    @classmethod
    def arg_parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(add_help=False)
        cls.add_arguments(parser)
        return parser

    @classmethod
    def add_arguments(cls, parser) -> None:
        for item in fields(cls):
            metadata = item.metadata
            options = [f'--{item.name}', f'--{item.name.replace("_", "-")}']
            if item.type is bool or metadata.get('kind') in ('bool', 'flag'):
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
    def from_args(cls, argv: Sequence[str], defaults=None):
        parsed, _ = cls.arg_parser().parse_known_args(list(argv))
        base = cls() if defaults is None else defaults
        values = {}
        given = set()
        for item in fields(cls):
            raw = getattr(parsed, item.name)
            if raw is None:
                continue
            default = getattr(base, item.name)
            values[item.name] = parse_setting(item, raw, default)
            given.add(item.name)
        return replace(base, **values), given
