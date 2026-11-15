# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Helpers for dataclass-backed RQt settings."""

import argparse
from dataclasses import dataclass, fields, replace, Field
from typing import Any, Callable, Sequence, Self

from cras_rqt_common.settings_fields import SettingsField


@dataclass
class SettingsBase:
    """
    Common persistence and command-line parsing for settings dataclasses.

    Every setting of a settings class is described by a settings field, which is what knows how
    the value is understood when it comes from the rqt settings or from the command line, how it is
    asked for in the configuration dialog and how it is written back.
    """

    @classmethod
    def fields_by_section(cls, hidden: Callable[[Field], bool] | None = None) -> \
            dict[str, list[SettingsField[Any, Any, Any, Any]]]:
        """
        The settings of this class, in the order they are declared, ready to be shown in a dialog.

        :param hidden: which settings to leave out, such as the ones a certain kind of a widget has no use for
        """
        by_section: dict[str, list[SettingsField[Any, Any, Any, Any]]] = {}
        for item in fields(cls):
            if (hidden is None or not hidden(item)) and isinstance(item, SettingsField):
                by_section.setdefault(item.section, []).append(item)
        return by_section

    def save(self, proxy) -> None:
        """Store these settings through the rqt settings proxy.

        :param proxy: The settings proxy to use.
        """
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(item, SettingsField):
                value = item.save(value)
            proxy.set_value(item.name, value)

    @classmethod
    def load(cls, proxy, defaults=None):
        """Read settings from the rqt settings proxy, falling back to the given ones.

        :param proxy: The settings proxy to use.
        :param defaults: The default settings to use if the proxy does not have a value for a setting.
        """
        base = cls() if defaults is None else defaults
        values = {}
        for item in fields(cls):
            default = getattr(base, item.name)
            value = proxy.value(item.name, default)
            if isinstance(item, SettingsField):
                value = item.load(value, default)
            values[item.name] = value
        return cls(**values)

    def with_widget_values(self, values: dict[str, Any]) -> Self:
        """
        Return these settings with the values a configuration dialog has just read from its widgets.

        :param values: Values read out from the settings widgets using :meth:`SettingsField.read_widget`.
        """
        return replace(self, **values)

    @classmethod
    def arg_parser(cls) -> argparse.ArgumentParser:
        """A parser that knows the command line options of all settings of this class."""
        parser = argparse.ArgumentParser(add_help=False)
        cls.add_arguments(parser)
        return parser

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Add a command line option for every setting of this class."""
        for item in fields(cls):
            if isinstance(item, SettingsField):
                item.add_to_arg_parser(parser)

    @classmethod
    def from_args(cls, argv: Sequence[str], defaults=None):
        """
        Take the settings that are given on the command line, leaving the rest as they are.

        :returns: the settings to use and the names of the settings the command line asked for
        """
        parsed, _ = cls.arg_parser().parse_known_args(list(argv))
        base = cls() if defaults is None else defaults
        values = {}
        given = set()
        for item in fields(cls):
            value = getattr(parsed, item.name)
            if value is None:
                continue
            default = getattr(base, item.name)
            if isinstance(item, SettingsField):
                value = item.load(value, default)
            values[item.name] = value
            given.add(item.name)
        return replace(base, **values), given
