# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Tests of the settings a plugin can be told to change."""

import math
import os
from typing import Any
from unittest.mock import patch

# The tests build real widgets, but we don't want to show them on a machine with a display.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from dataclasses import dataclass, fields  # noqa: E402
from itertools import groupby  # noqa: E402
import pytest  # noqa: E402

from cras_rqt_common.color import to_color, to_optional_color, Color  # noqa: E402
from cras_rqt_common.color_widgets import ColorButton  # noqa: E402
from cras_rqt_common.settings import SettingsBase  # noqa: E402
from cras_rqt_common.settings_dialog import SettingsDialog  # noqa: E402
from cras_rqt_common.settings_fields import (  # noqa: E402
    BoolField, ChoiceField, FloatField, IntField, OptionalColorField, RequiredColorField, TextField,
    parse_color, to_bool, to_int, to_float, SettingsField)
from cras_rqt_common.settings_widget import SettingsWidget  # noqa: E402
from python_qt_binding.QtGui import QColor  # noqa: E402
from python_qt_binding.QtWidgets import (  # noqa: E402
    QCheckBox, QComboBox, QApplication, QDialog, QDoubleSpinBox, QLineEdit, QSpinBox, QWidget)


class SettingsProxy:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def set_value(self, name, value):
        self.values[name] = value

    def value(self, name, default=None):
        return self.values.get(name, default)


def get_field(cls, name: str) -> SettingsField:
    for f in fields(cls):
        if f.name == name:
            if isinstance(f, SettingsField):
                return f
            assert False, f'Field {name} in {cls} is not a SettingsField'
    assert False, f'Field {name} not found in {cls}'


def get_fields(cls) -> dict[str, SettingsField[Any, Any, Any, Any]]:
    return dict((field.name, get_field(cls, field.name)) for field in fields(cls))


@pytest.fixture(scope='module')
def app():
    """A Qt application to build the widgets the settings ask for with."""
    return QApplication.instance() or QApplication([])


@dataclass
class ExampleSettings(SettingsBase):
    count: int = IntField(3, 'Count', 'How many times to try.', 'Counting',  # type: ignore[bad-assignment]
                          limits=(0, 10))
    ratio: float = FloatField(0.5, 'Ratio', 'How much of it to take.', 'Counting',  # type: ignore[bad-assignment]
                              limits=(0.0, 1.0), step=0.1, suffix=' ×', decimals=1)
    label: str = TextField('example', 'Label', 'What to write.', '', allow_empty=True)  # type: ignore[bad-assignment]


@dataclass
class ParsedSettings(SettingsBase):
    enabled: bool = BoolField(True, 'Enabled', 'Whether it is on.', 'Switches')  # type: ignore[bad-assignment]
    topic: str = TextField('input', 'Topic', 'Where it is coming from.', 'Topic',  # type: ignore[bad-assignment]
                           allow_empty=True)
    count: int = IntField(3, 'Count', 'How many times to try.', 'Numbers',  # type: ignore[bad-assignment]
                          limits=(1, 10))
    alignment: int = ChoiceField(1, 'Alignment', 'Where it is.', 'Numbers',  # type: ignore[bad-assignment]
                                 ((0, 'Left'), (1, 'Center'), (2, 'Right')))
    hold_delay_ms: int = IntField(250, 'Hold delay', 'How long it takes to hold.',  # type: ignore[bad-assignment]
                                  'Numbers', limits=(50, 2000), step=50, suffix=' ms')  # type: ignore[bad-assignment]
    color: Color | None = OptionalColorField(None, 'Color', 'Which color.', 'Colors')  # type: ignore[bad-assignment]
    frame: Color = RequiredColorField(Color('#00ff00'), 'Frame',  # type: ignore[bad-assignment]
                                      'Which color goes around it.', 'Colors')


def test_save_dataclass_settings_to_rqt_proxy():
    proxy = SettingsProxy()
    ExampleSettings(count=7).save(proxy)
    assert proxy.values == {'count': 7, 'ratio': 0.5, 'label': 'example'}


def test_load_dataclass_settings_uses_defaults():
    proxy = SettingsProxy()
    proxy.values['count'] = '8'
    loaded = ExampleSettings.load(proxy, defaults=ExampleSettings(count=5, label='custom'))
    assert loaded == ExampleSettings(count=8, label='custom')


def test_a_field_describes_the_setting_it_is_written_for():
    topic = get_field(ParsedSettings, 'topic')
    assert topic.name == 'topic'
    assert topic.type is str
    assert topic.default == 'input'
    assert ParsedSettings().topic == 'input'


def test_the_settings_of_one_section_are_declared_next_to_each_other():
    # a configuration dialog shows a heading per section and reads the sections one after the other,
    # which only works while the settings of one section are not split by settings of another one
    sections = {section: [item.name for item in group] for section, group in
                groupby(fields(ParsedSettings), key=lambda item: item.section)}
    assert list(sections) == ['Switches', 'Topic', 'Numbers', 'Colors']
    assert sections['Numbers'] == ['count', 'alignment', 'hold_delay_ms']
    assert sections['Colors'] == ['color', 'frame']


def test_stored_values_are_understood_by_the_field_of_every_setting():
    proxy = SettingsProxy()
    proxy.values.update({'enabled': 'off', 'topic': '  ', 'count': '100', 'alignment': '2',
                         'color': '#010203', 'frame': 'not a color at all'})
    assert ParsedSettings.load(proxy) == ParsedSettings(
        enabled=False, topic='', count=10, alignment=2, color=Color('#010203'), frame=Color('#00ff00'))


def test_a_value_that_makes_no_sense_leaves_the_setting_as_it_was():
    defaults = ParsedSettings(enabled=True, count=4, alignment=2, color=Color('magenta'))
    kept = ParsedSettings.load(SettingsProxy(), defaults=defaults)
    assert kept == defaults
    broken = SettingsProxy()
    broken.values.update({'enabled': 'maybe', 'count': 'a lot', 'alignment': 'middle'})
    assert ParsedSettings.load(broken, defaults=defaults) == defaults


def test_a_color_that_makes_no_sense_is_no_color_at_all():
    # a color that can be taken away has nothing to tell apart a value nobody understands from one
    # that was taken away on purpose, so both of them leave the setting without a color
    broken = SettingsProxy()
    broken.values.update({'color': 'not a color at all', 'frame': 'not a color either'})
    settings = ParsedSettings.load(broken)
    assert settings.color is None
    # a color that has to be there falls back to the one it is given
    assert settings.frame == ParsedSettings().frame


def test_settings_base_command_line_parser_uses_the_same_field_converters():
    settings, given = ParsedSettings.from_args(
        ['--topic', '/mission/text', '--count', '20', '--alignment', '2', '--color', '#010203',
         '--somebody-elses-argument', 'whatever'])
    # a switch reports itself whether the command line mentioned it or not, and one nobody mentioned
    # reads as off; the settings classes of the plugins undo that for their own switches
    assert settings == ParsedSettings(enabled=False, topic='/mission/text', count=10, alignment=2,
                                      color=Color('#010203'))
    assert given == {'enabled', 'topic', 'count', 'alignment', 'color'}
    assert get_field(ParsedSettings, 'enabled').load('unknown', True)


def test_a_setting_can_be_asked_for_with_underscores_and_dashes_alike():
    # rqt's own arguments use dashes, so both forms of a setting name are understood
    dashes, given = ParsedSettings.from_args(['--topic', '/mission/text', '--hold-delay-ms', '90'])
    assert (dashes.topic, dashes.hold_delay_ms) == ('/mission/text', 90)
    assert given == {'enabled', 'topic', 'hold_delay_ms'}
    underscores, _ = ParsedSettings.from_args(['--hold_delay_ms', '90'])
    assert underscores.hold_delay_ms == 90


def test_a_switch_does_not_need_a_value_of_its_own():
    on, given = ParsedSettings.from_args(['--enabled'], defaults=ParsedSettings(enabled=False))
    assert on.enabled
    assert given == {'enabled'}


def test_a_dialog_reads_its_widgets_through_the_fields_of_the_settings(app):
    settings = ParsedSettings(topic='stored', count=3)
    count = get_field(settings, 'count')
    spin = QSpinBox()
    spin.setValue(7)
    # what the dialog hands over is what the field read out of its widget, so the value is already
    # of the type the setting holds
    changed = settings.with_widget_values({'topic': '/mission/text', 'count': count.read_widget(spin)})
    assert changed.topic == '/mission/text'
    assert changed.count == 7
    assert isinstance(changed.count, int)  # a count, not a decimal number
    assert changed.alignment == settings.alignment  # a setting the dialog does not show is kept
    assert settings.topic == 'stored'  # the settings the dialog started from are left alone


def test_a_field_builds_the_widget_that_suits_its_setting(app):
    declared = get_fields(ExampleSettings)
    text = declared['label'].create_widget(None, 'example')
    assert isinstance(text, QLineEdit)
    assert text.text() == 'example'
    whole = declared['count'].create_widget(None, 4)
    assert isinstance(whole, QSpinBox)
    assert whole.minimum() == 0
    assert whole.maximum() == 10
    decimal = declared['ratio'].create_widget(None, 0.5)
    assert isinstance(decimal, QDoubleSpinBox)
    assert decimal.suffix() == ' ×'
    assert decimal.decimals() == 1
    assert decimal.singleStep() == pytest.approx(0.1)
    switch = get_field(ParsedSettings, 'enabled').create_widget(None, True)
    assert isinstance(switch, QCheckBox)
    assert switch.isChecked()


def test_a_widget_hands_its_value_back_through_the_field_that_describes_it(app):
    declared = get_fields(ParsedSettings)
    text = declared['topic'].create_widget(None, 'input')
    text.setText('  /mission/text  ')
    assert declared['topic'].read_widget(text) == '/mission/text'
    count = declared['count'].create_widget(None, 3)
    count.setValue(7)
    assert declared['count'].read_widget(count) == 7
    assert isinstance(declared['count'].read_widget(count), int)
    switch = declared['enabled'].create_widget(None, False)
    switch.setChecked(True)
    assert declared['enabled'].read_widget(switch)
    choice = declared['alignment'].create_widget(None, 2)
    assert isinstance(choice, QComboBox)
    assert [choice.itemText(i) for i in range(choice.count())] == ['Left', 'Center', 'Right']
    assert choice.currentData() == 2
    choice.setCurrentIndex(0)
    assert declared['alignment'].read_widget(choice) == 0


def test_a_color_widget_shows_its_color_and_can_be_cleared_back(app):
    color = get_field(ParsedSettings, 'color')
    widget = color.create_widget(None, Color('#010203'))
    assert color.read_widget(widget) == Color('#010203')
    widget._clear.click()
    assert color.read_widget(widget) is None
    widget._button.set_color('red')
    assert color.read_widget(widget) == Color('red')


def test_a_color_that_cannot_be_taken_away_never_hands_out_nothing(app):
    frame = get_field(ParsedSettings, 'frame')
    widget = frame.create_widget(None, Color('#010203'))
    assert isinstance(widget, ColorButton)
    assert frame.read_widget(widget) == Color('#010203')
    assert frame.load('not a color', Color('red')) == Color('red')
    # what is stored is the color written the way Qt writes one, which is what rqt keeps as text
    assert frame.save(Color('#010203')) == '#010203'
    assert frame.save(Color('red')) == '#ff0000'


def test_to_number_uses_default_for_invalid_values_and_clamps_limits():
    assert to_int('bad', 4, (0, 10)) == 4
    assert to_float('nan', 4.0, (0.0, 10.0), True) == 4.0
    assert math.isnan(to_float('nan', 4.0, (0.0, 10.0), False))
    assert to_int(float('inf'), 4, (0, 10)) == 4
    assert to_int('-2', 4, (0, 10)) == 0
    assert to_int('12', 4, (0, 10)) == 10


def test_to_bool_understands_the_words_people_use_and_distrusts_the_rest():
    assert to_bool('yes', False)
    assert not to_bool('0', True)
    assert to_bool(True, False)
    assert to_bool('maybe', True)
    assert not to_bool('maybe', False)


def test_optional_color_hands_back_the_color_or_nothing_at_all():
    assert to_optional_color(Color('red')) == Color('red')
    assert to_optional_color((1, 2, 3)) == Color(1, 2, 3)
    assert to_optional_color([1, 2, 3]) == Color(1, 2, 3)
    # the channels written as fractions are counted down to whole numbers
    assert to_optional_color((1.0, 0.0, 0.0, 0.5)) == Color(255, 0, 0, 127)
    assert to_optional_color('not a color') is None
    assert to_optional_color('   ') is None
    assert to_optional_color(None) is None


def test_a_color_that_has_to_be_there_falls_back_to_the_given_one():
    assert to_color('#010203', Color('gray')) == Color('#010203')
    assert to_color('not a color', Color('gray')) == Color('gray')
    assert to_color(None, None) == Color('gray')  # there was no color to fall back to either


def test_color_parser_hands_out_colors_and_knows_no_color():
    assert parse_color('#010203', None) == Color('#ff010203')
    assert parse_color('#01020304', None) == Color('#01020304')
    assert parse_color('', None) is None
    assert parse_color('   ', None) is None
    # a color that cannot be taken away is looked for in the default it is given
    assert parse_color('not a color', Color('red'), optional=False) == Color('red')
    assert get_field(ParsedSettings, 'topic').load('  text  ', '') == 'text'


@dataclass
class DialogSettings(SettingsBase):
    """Settings of every kind a dialog has to show, in the sections it has to tell apart."""

    topic: str = TextField('input', 'Topic', 'Where it is coming from.', 'Where',  # type: ignore[bad-assignment]
                           allow_empty=True)
    enabled: bool = BoolField(True, 'Enabled', 'Whether it is on.', 'How')  # type: ignore[bad-assignment]
    count: int = IntField(3, 'Count', 'How many times to try.', 'How', limits=(1, 10))  # type: ignore[bad-assignment]
    ratio: float = FloatField(0.5, 'Ratio', 'How much of it to take.', 'How',  # type: ignore[bad-assignment]
                              limits=(0.0, 1.0), step=0.1, decimals=1, suffix=' ×')
    alignment: int = ChoiceField(1, 'Alignment', 'Where it is.', 'How',  # type: ignore[bad-assignment]
                                 ((0, 'Left'), (1, 'Center'), (2, 'Right')))
    color: Color | None = OptionalColorField(None, 'Color', 'Which color.', 'Colors')  # type: ignore[bad-assignment]
    frame: Color = RequiredColorField(Color('#00ff00'), 'Frame',  # type: ignore[bad-assignment]
                                      'Which color goes around it.', 'Colors')


class OneSectionOnly(SettingsDialog):
    """A dialog that leaves one setting out and offers another one only while a switch says so."""

    TITLE = 'Example configuration'

    def __init__(self, settings, title: str = None, parent: QWidget = None, ask_for_ratio: bool = False):
        self._ask_for_ratio = ask_for_ratio
        super().__init__(settings, title, parent)

    def hidden(self, item: SettingsField) -> bool:
        return item.name == 'frame'

    def setup(self) -> None:
        self.widget('enabled').toggled.connect(self._offer_ratio)
        self._offer_ratio(self.widget('enabled').isChecked())

    def _offer_ratio(self, enabled: bool) -> None:
        self.widget('ratio').setEnabled(enabled and self._ask_for_ratio)


def test_the_dialog_asks_for_every_setting_under_the_heading_of_its_section(app):
    dialog = SettingsDialog(DialogSettings(), 'Dialog configuration')
    app.processEvents()
    assert dialog.windowTitle() == 'Dialog configuration'
    assert dialog.settings_names() == {'topic', 'enabled', 'count', 'ratio', 'alignment', 'color', 'frame'}
    # what belongs together is shown together, and each setting is reachable by its name
    assert {'topic'} == set(dialog.widgets_of('Where')) - {'heading_0'}
    assert {'enabled', 'count', 'ratio', 'alignment'} <= set(dialog.widgets_of('How'))
    assert dialog.widget('topic').text() == 'input'
    assert dialog.widget('count').value() == 3
    assert dialog.widget('alignment').currentData() == 1
    # the description of the setting is what the widget says about itself
    assert dialog.widget('count').toolTip() == get_field(DialogSettings, 'count').description


def test_the_dialog_hands_back_the_settings_that_were_filled_in(app):
    settings = DialogSettings(topic='stored', count=2, color=Color('#2e7d32'))
    dialog = SettingsDialog(settings, parent=None)
    # a dialog changes a copy, so the settings it was opened with are left as they were
    assert dialog.settings() == settings
    assert settings.topic == 'stored'

    dialog.widget('topic').setText('/mission/text')
    dialog.widget('enabled').setChecked(False)
    dialog.widget('count').setValue(7)
    dialog.widget('ratio').setValue(0.8)
    dialog.widget('alignment').setCurrentIndex(2)
    dialog.widget('color').set_color(QColor('blue'))
    changed = dialog.settings()
    assert changed == DialogSettings(topic='/mission/text', enabled=False, count=7, ratio=0.8, alignment=2,
                                     color=Color('blue'))
    assert isinstance(changed.count, int)  # a count is a whole number, not a decimal one
    assert changed.frame == settings.frame  # a setting the dialog showed is read back as it is filled in


def test_a_setting_the_dialog_leaves_out_keeps_the_value_it_was_opened_with(app):
    settings = DialogSettings(frame=Color('#ff0000'))
    dialog = OneSectionOnly(settings, ask_for_ratio=True)
    # a setting the dialog does not ask for is neither shown nor made up
    assert 'frame' not in dialog.settings_names()
    assert dialog.settings().frame == Color('#ff0000')
    # and what the dialog offers on its own depends on what the user switched
    assert dialog.widget('ratio').isEnabled()
    dialog.widget('enabled').setChecked(False)
    assert not dialog.widget('ratio').isEnabled()
    dialog.widget('enabled').setChecked(True)
    assert dialog.widget('ratio').isEnabled()
    # a dialog that was not asked to offer the setting never does
    other = OneSectionOnly(settings, ask_for_ratio=False)
    assert not other.widget('ratio').isEnabled()


def test_the_color_a_dialog_shows_is_the_color_it_was_given(app):
    dialog = SettingsDialog(DialogSettings(color=Color('#2e7d32')))
    chosen = dialog.widget('color')
    assert Color(chosen.color()) == Color('#2e7d32')
    assert chosen._clear.isEnabled()  # there is a color to take away
    dialog.widget('color').set_color(QColor('blue'))
    assert dialog.settings().color == Color('blue')
    chosen._clear.click()
    assert chosen.color() is None
    assert dialog.settings().color is None
    # a color that cannot be taken away has no button for taking it away
    frame = dialog.widget('frame')
    assert isinstance(frame, ColorButton)
    assert Color(frame.color()) == Color('#00ff00')


def test_a_dialog_leaves_the_widgets_it_shows_look_like_themselves(app):
    # a style sheet set on a widget paints everything inside it as well, so the color of a setting
    # must never end up painted over the dialog itself
    dialog = SettingsDialog(DialogSettings(color=Color('#2e7d32')))
    dialog.show()
    app.processEvents()
    assert dialog.styleSheet() == ''
    for widget in dialog.findChildren(QWidget):
        assert widget.styleSheet() == '', f'{type(widget).__name__} paints over the look of the Qt style'


class ExampleWidget(SettingsWidget[DialogSettings, SettingsDialog]):
    """A widget that only remembers what it was told to show."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent, 'Example')
        self.shown = []

    def apply_settings(self, settings: SettingsBase) -> None:
        super().apply_settings(settings)
        self.shown.append(settings)


class AnsweringDialog(SettingsDialog):
    """
    A configuration dialog that closes as it is told to, without waiting for anybody.

    :ivar answers: whether the user presses the button that agrees to what is filled in
    :ivar typed: what the user types into the settings with the given name, if any
    """

    answers = QDialog.DialogCode.Accepted
    typed: dict = {}
    opened: list = []

    def exec(self) -> int:
        type(self).opened.append(self)
        for name, value in type(self).typed.items():
            self.widget(name).setText(value)
        return type(self).answers


def test_a_widget_shows_what_the_configuration_dialog_handed_back(app):
    widget = ExampleWidget()
    AnsweringDialog.opened = []
    AnsweringDialog.answers = QDialog.DialogCode.Accepted
    AnsweringDialog.typed = {}
    with patch.object(ExampleWidget, 'DIALOG_TYPE', AnsweringDialog):
        widget.open_configuration()
    assert len(AnsweringDialog.opened) == 1
    dialog = AnsweringDialog.opened[0]
    # the window says what the widget it belongs to is for, and the settings it shows are the ones
    # the widget is showing right now
    assert dialog.windowTitle() == 'Example configuration'
    assert dialog.settings() == DialogSettings()
    # agreeing to the settings as they are is still telling the widget to show them
    assert widget.shown == [DialogSettings()]

    AnsweringDialog.typed = {'topic': '/mission/text'}
    with patch.object(ExampleWidget, 'DIALOG_TYPE', AnsweringDialog):
        widget.open_configuration()
    assert widget.settings().topic == '/mission/text'
    assert widget.shown[-1] == widget.settings()

    # what the user cancels is not shown either
    AnsweringDialog.answers = QDialog.DialogCode.Rejected
    AnsweringDialog.typed = {'topic': '/mission/cancelled'}
    with patch.object(ExampleWidget, 'DIALOG_TYPE', AnsweringDialog):
        widget.open_configuration()
    assert widget.settings().topic == '/mission/text'
    assert len(widget.shown) == 2


def test_a_widget_stores_what_it_shows_and_loads_it_back(app):
    widget = ExampleWidget()
    assert widget.settings() == DialogSettings()
    assert widget.windowTitle() == 'Example'

    proxy = SettingsProxy()
    widget.apply_settings(DialogSettings(topic='/mission/text', count=4, color=Color('#2e7d32')))
    widget.save_settings(None, proxy)
    assert proxy.values['topic'] == '/mission/text'
    assert proxy.values['count'] == 4
    assert proxy.values['color'] == Color('#2e7d32').name()

    other = ExampleWidget()
    # what rqt kept is text, and the widget starts showing it right away
    other.restore_settings(None, SettingsProxy({name: str(value) for name, value in proxy.values.items()}))
    assert other.settings() == DialogSettings(topic='/mission/text', count=4, color=Color('#2e7d32'))
    # and a setting nobody stored is left as the widget has it
    other.restore_settings(None, SettingsProxy({'topic': '/mission/other'}))
    assert other.settings().topic == '/mission/other'
    assert other.settings().count == 4
