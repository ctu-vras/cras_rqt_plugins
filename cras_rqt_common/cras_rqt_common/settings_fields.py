# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The settings a plugin can be told to change, each knowing how to handle its one setting."""

import math
import sys
from argparse import ArgumentParser
from dataclasses import Field, MISSING
from typing import Any, Generic, Sequence, Tuple

from typing_extensions import TypeVar

from cras_rqt_common.color import to_color, to_optional_color, ColorSettingsType, Color
from cras_rqt_common.color_widgets import CLEAR_TIP, ColorButton, ColorEditor
from python_qt_binding.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox, QWidget

ValueType = TypeVar('ValueType')
WidgetType = TypeVar('WidgetType', bound=QWidget)
SettingsType = TypeVar('SettingsType', default=ValueType)
ArgumentType = TypeVar('ArgumentType', default=SettingsType)

NumericType = TypeVar('NumericType', int, float)

TRUE_WORDS = ('1', 'true', 'yes', 'on')
FALSE_WORDS = ('0', 'false', 'no', 'off')


def to_int(value: ValueType, default: int, limits: tuple[int| None, int | None] | None) -> int:
    """Parse and clamp a numeric setting, returning its default when it is malformed."""
    try:
        number = int(value)
    except Exception:
        return int(default)
    if limits is None or len(limits) == 0:
        return number
    if len(limits) > 0 and limits[0] is not None:
        number = max(number, int(limits[0]))
    if len(limits) > 1 and limits[1] is not None:
        number = min(number, int(limits[1]))
    return number


def to_float(
        value: ValueType, default: NumericType, limits: tuple[NumericType | None, NumericType | None] | None,
        only_finite: bool = False) -> float:
    """Parse and clamp a numeric setting, returning its default when it is malformed."""
    try:
        number = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(number) and only_finite:
        return float(default)
    if limits is None or len(limits) == 0:
        return number
    if len(limits) > 0 and limits[0] is not None:
        number = max(number, float(limits[0]))
    if len(limits) > 1 and limits[1] is not None:
        number = min(number, float(limits[1]))
    return number


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


def parse_color(value: ColorSettingsType | None, default: Color | None, *, optional: bool = True) -> Color | None:
    """Parse a color setting."""
    if optional:
        return to_optional_color(value)
    return to_color(value, default)


class SettingsField(Field[ValueType], Generic[ValueType, WidgetType, SettingsType, ArgumentType]):
    """
    One setting of a settings class and everything that is known about it.

    A field is written in place of the usual ``field()`` of a dataclass, right next to the setting
    it describes, so that the setting says at once what it holds, how it is asked for and how it is
    read back. It is a dataclass field, so the name and the type of the setting are filled in by
    the settings class around it and a field always describes the one setting it is written for.

    :param default: what the setting holds while nobody says anything about it
    :param label: what the setting is called in the configuration dialog
    :param description: what the setting is told to the user, both in the dialog and on the command line
    :param section: what part of the configuration dialog the setting belongs to, empty for default section
    :param kwargs: extra field metadata
    """

    def __init__(self, default: ValueType, label: str, description: str, section: str, **kwargs: Any) -> None:
        # Python 3.14 added constructor arg doc
        extra = {}
        if sys.version_info >= (3, 14):
            extra['doc'] = description
        super().__init__(default=default, default_factory=MISSING, init=True, repr=True,
                         hash=True, compare=True, metadata=dict(kwargs), kw_only=False, **extra)
        self.label = label
        self.description = description
        self.section = section

    def load(self, value: SettingsType | None, default: ValueType) -> ValueType:
        """
        Return the stored or commanded value as something the plugin can work with.

        :param value: what was found for this setting, or nothing at all
        :param default: what to use while the setting holds nothing usable
        """
        return default if value is None else value

    def save(self, value: ValueType) -> SettingsType:
        """Return what should be stored for this setting."""
        return value

    def create_widget(self, parent: QWidget | None, initial_value: ValueType) -> WidgetType:
        """
        Create the widget that lets the user set this setting, or nothing when it cannot be edited.

        :param parent: the widget the created one belongs to
        :param initial_value: the value the widget should start with
        """
        raise NotImplementedError

    def read_widget(self, widget: WidgetType) -> ValueType:
        """Return what the widget created by :meth:`create_widget` holds now."""
        return None

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        """Add a command line option that sets this setting."""
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, metavar='VALUE', help=self.description)

    def _arg_parser_options_names(self) -> list:
        # rqt's own arguments use dashes, so we accept both forms to avoid surprises
        return [f'--{self.name.replace("_", "-")}', f'--{self.name}']


class TextField(SettingsField[str, QLineEdit]):
    """
    A setting that holds a string.

    :param allow_empty: Whether empty strings are allowed values.
    """

    def __init__(self, default: str, label: str, description: str, section: str, allow_empty: bool = True) -> None:
        super().__init__(default, label, description, section)
        self.allow_empty = allow_empty

    def load(self, value: str | None, default: str) -> str:
        if value is None:
            return default
        value = str(value).strip()
        if not value and not self.allow_empty:
            return default
        return value

    def create_widget(self, parent: QWidget | None, initial_value: str) -> QLineEdit:
        widget = QLineEdit(str(initial_value), parent)
        widget.setClearButtonEnabled(True)
        return widget

    def read_widget(self, widget: QLineEdit) -> str:
        return widget.text().strip()

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, metavar='TEXT', help=self.description)


class BoolField(SettingsField[bool, QCheckBox, bool | int | str, bool]):
    """A setting that is either on or off."""

    def load(self, value: bool | int | str | None, default: bool) -> bool:
        return to_bool(value, default)

    def create_widget(self, parent: QWidget | None, initial_value: bool) -> QCheckBox:
        widget = QCheckBox(parent)
        widget.setChecked(bool(initial_value))
        return widget

    def read_widget(self, widget: QCheckBox) -> bool:
        return widget.isChecked()

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, action='store_true',
                            help=self.description)


class IntField(SettingsField[int, QSpinBox, int | str]):
    """
    A setting that holds an integer which is only asked for within known limits.

    :param limits: the smallest and the largest number that still makes sense (None means no limit)
    :param step: how much one turn of the spin box changes the number by
    :param suffix: what is written after the number, such as the unit it is measured in
    """

    def __init__(self, default: int, label: str, description: str, section: str,
                 limits: tuple[int | None, int | None] | None = None, step: int = 1, suffix: str = ''):
        super().__init__(default, label, description, section)
        self.limits = limits
        self.step = step
        self.suffix = suffix

    def load(self, value: int | str | None, default: int) -> int:
        return to_int(value, default, self.limits)

    def create_widget(self, parent: QWidget | None, initial_value: int) -> QSpinBox:
        widget = QSpinBox(parent)
        min_limit = int(self.limits[0]) if (self.limits and self.limits[0] is not None) else -sys.maxsize
        max_limit = int(self.limits[1]) if (self.limits and self.limits[1] is not None) else sys.maxsize
        widget.setRange(min_limit, max_limit)
        widget.setSingleStep(int(self.step))
        widget.setSuffix(self.suffix)
        widget.setValue(int(initial_value))
        return widget

    def read_widget(self, widget: QSpinBox) -> int:
        return int(widget.value())

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, type=int, metavar='NUMBER',
                            help=self.description)


class FloatField(SettingsField[NumericType, QDoubleSpinBox, NumericType | str]):
    """
    A setting that holds a float number which is only asked for within known limits.

    :param limits: the smallest and the largest number that still makes sense (None or non-finite means no limit)
    :param step: how much one turn of the spin box changes the number by
    :param suffix: what is written after the number, such as the unit it is measured in
    :param decimals: how many decimal places to show, which a count of things has none of
    :param only_finite: whether to only accept finite numbers
    """

    def __init__(self, default: NumericType, label: str, description: str, section: str,
                 limits: Tuple[NumericType | None, NumericType | None] | None = None, step: NumericType = 1.0,
                 suffix: str = '', decimals: int = 2, only_finite: bool = True) -> None:
        super().__init__(default, label, description, section)
        self.limits = limits
        self.step = float(step)
        self.suffix = str(suffix)
        self.decimals = int(decimals)
        self.only_finite = only_finite

    def load(self, value: NumericType | None, default: NumericType) -> float:
        return to_float(value, default, self.limits, self.only_finite)

    def get_limit(self, i: int) -> float:
        no_limit = -math.inf if i == 0 else math.inf
        if self.limits is None:
            return no_limit
        if len(self.limits) <= i:
            return no_limit
        if self.limits[i] is None or not math.isfinite(self.limits[i]):
            return no_limit
        return float(self.limits[i])

    def create_widget(self, parent: QWidget | None, initial_value: NumericType) -> QDoubleSpinBox:
        widget = QDoubleSpinBox(parent)
        widget.setRange(self.get_limit(0), self.get_limit(1))
        widget.setSingleStep(self.step)
        widget.setDecimals(self.decimals)
        widget.setSuffix(self.suffix)
        widget.setValue(float(initial_value))
        return widget

    def read_widget(self, widget: QDoubleSpinBox) -> float:
        value = float(widget.value())
        if self.only_finite and not math.isfinite(value):
            return float(self.default)
        return value

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, type=float, metavar='NUMBER',
                            help=self.description)


class ChoiceField(SettingsField[ValueType, QComboBox, ValueType | str, ValueType | str]):
    """
    A setting that is one of a few known values.

    :param options: the values to choose from, each with the text that shows it
    """

    def __init__(self, default: ValueType, label: str, description: str, section: str,
                 options: Sequence[tuple[ValueType, str]]) -> None:
        super().__init__(default, label, description, section)
        self.options = tuple(options)

    def load(self, value: ValueType | str | None, default: ValueType) -> ValueType:
        if value is None:
            return default
        for option, _ in self.options:
            # what was stored or given on the command line is text, so the option is looked for in its text as well
            if option == value or str(option) == str(value).strip():
                return option
        return default

    def create_widget(self, parent: QWidget | None, initial_value: ValueType) -> QComboBox:
        widget = QComboBox(parent)
        widget.setEditable(False)
        for option, option_label in self.options:
            widget.addItem(option_label, option)
        index = widget.findData(initial_value)
        widget.setCurrentIndex(index if index >= 0 else -1)
        return widget

    def read_widget(self, widget: QComboBox) -> ValueType:
        return widget.currentData()

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        options = self._arg_parser_options_names()
        if self.type in (int, float):
            parser.add_argument(*options, dest=self.name, type=self.type, metavar='NUMBER', help=self.description)
        else:
            parser.add_argument(*options, dest=self.name, metavar='TEXT', help=self.description)


class RequiredColorField(SettingsField[Color, ColorButton, ColorSettingsType, str]):
    """A setting that holds a color, written the way Qt writes one."""

    def load(self, value: ColorSettingsType | None, default: Color) -> Color:
        return to_color(value, default)

    def save(self, value: Color) -> ColorSettingsType:
        return value.name()

    def create_widget(self, parent: QWidget | None, initial_value: Color) -> ColorButton:
        return ColorButton(initial_value.q(), parent)

    def read_widget(self, widget: ColorButton) -> Color:
        return Color(widget.color())

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, metavar='COLOR', help=self.description)


class OptionalColorField(SettingsField[Color | None, ColorEditor, ColorSettingsType | None, str]):
    """
    A setting that holds a color, written the way Qt writes one.

    :param clear_tip: what the button that takes the color away says, for a plugin that knows what
        happens while it has no color of its own
    """

    def __init__(self, default: Color | None, label: str, description: str, section: str, clear_tip: str | None = None):
        super().__init__(default, label, description, section)
        self.clear_tip = clear_tip

    def load(self, value: ColorSettingsType | None, default: Color | None) -> Color | None:
        return to_optional_color(value)

    def save(self, value: Color | None) -> ColorSettingsType | None:
        return value.name() if value is not None else None

    def create_widget(self, parent: QWidget | None, initial_value: Color | None) -> ColorEditor:
        return ColorEditor(initial_value.q() if initial_value is not None else None, parent,
                           CLEAR_TIP if self.clear_tip is None else self.clear_tip)

    def read_widget(self, widget: ColorEditor) -> Color | None:
        return Color(widget.color()) if widget.color() is not None else None

    def add_to_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(*self._arg_parser_options_names(), dest=self.name, metavar='COLOR', help=self.description,
                            required=False)
