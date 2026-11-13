# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

from dataclasses import dataclass, field

from cras_rqt_common.color import to_optional_color
from cras_rqt_common.settings import (SettingsBase, load_settings, parse_setting, save_settings,
                                      to_number)
from python_qt_binding.QtGui import QColor


class SettingsProxy:
    def __init__(self):
        self.values = {}

    def set_value(self, name, value):
        self.values[name] = value

    def value(self, name, default=None):
        return self.values.get(name, default)


@dataclass
class ExampleSettings(SettingsBase):
    count: int = field(default=3, metadata={'limits': (0, 10)})
    label: str = field(default='example', metadata={'allow_empty': True})


@dataclass
class ParsedSettings(SettingsBase):
    enabled: bool = field(default=True, metadata={'kind': 'flag'})
    topic: str = field(default='input', metadata={'allow_empty': True})
    count: int = field(default=3, metadata={'limits': (1, 10)})
    alignment: int = field(default=1, metadata={
        'kind': 'choice', 'options': ((0, 'Left'), (1, 'Center'), (2, 'Right'))})
    color: str = field(default='', metadata={'kind': 'color', 'optional': True})


def test_save_dataclass_settings_to_rqt_proxy():
    proxy = SettingsProxy()
    save_settings(ExampleSettings(count=7), proxy)
    assert proxy.values == {'count': 7, 'label': 'example'}


def test_load_dataclass_settings_uses_common_metadata_parser_and_defaults():
    proxy = SettingsProxy()
    proxy.values['count'] = '8'
    loaded = load_settings(ExampleSettings, proxy, defaults=ExampleSettings(count=5, label='custom'))
    assert loaded == ExampleSettings(count=8, label='custom')


def test_settings_base_load_parses_field_metadata_consistently():
    proxy = SettingsProxy()
    proxy.values.update({'enabled': 'off', 'topic': '  ', 'count': '100',
                         'alignment': '2', 'color': '#010203'})
    assert ParsedSettings.load(proxy) == ParsedSettings(
        enabled=False, topic='', count=10, alignment=2, color='#ff010203')
    assert parse_setting(ParsedSettings.__dataclass_fields__['enabled'], 'unknown', True)


def test_settings_base_command_line_parser_uses_the_same_field_converters():
    settings, given = ParsedSettings.from_args(
        ['--enabled', 'off', '--count', '20', '--alignment', '2'])
    assert settings == ParsedSettings(enabled=False, count=10, alignment=2)
    assert given == {'enabled', 'count', 'alignment'}


def test_to_number_uses_default_for_invalid_values_and_clamps_limits():
    assert to_number('bad', 4, (0, 10), int) == 4
    assert to_number('-2', 4, (0, 10), int) == 0
    assert to_number('12', 4, (0, 10), int) == 10


def test_optional_color_returns_a_copy_and_rejects_invalid_values():
    original = QColor('red')
    color = to_optional_color(original)
    assert color == original
    assert color is not original
    assert to_optional_color('not a color') is None


def test_color_parser_always_returns_argb_and_strings_are_always_stripped():
    from cras_rqt_common.settings import parse_color

    color_field = ParsedSettings.__dataclass_fields__['topic']
    assert parse_color('#010203', '') == '#ff010203'
    assert parse_color('#01020304', '') == '#01020304'
    assert parse_setting(color_field, '  text  ', '') == 'text'
