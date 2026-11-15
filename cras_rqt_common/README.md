# cras_rqt_common

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

The parts the RQt plugins in this repository share: a color that can live in a settings dataclass, the settings a
plugin can be told to change, the dialog asking for them, the widget showing them and the plugin around such a
widget. Nothing here knows anything about buttons, texts or camera gimbals. A plugin says what its settings are and
what to do with them, and this package is what makes all of them behave the same way, so it holds no plugin itself.

## What is in here

| Module | What it gives the plugins |
|---|---|
| `color.py` | `Color`, an immutable color, and `to_color()` / `to_optional_color()` to read a color out of whatever the user or a message gave |
| `settings_fields.py` | the field types a settings class is built of, each knowing its dialog widget, its command line option, and how its value is stored and read back |
| `settings.py` | `SettingsBase`, the dataclass base that saves all settings, loads them and parses them from the command line |
| `color_widgets.py` | the color pickers of the settings dialog, with the button that takes a color away |
| `settings_dialog.py` | `SettingsDialog`, asking for all settings of a settings class |
| `settings_widget.py` | `SettingsWidget`, the widget that opens that dialog and stores what the user chose |
| `settings_plugin.py` | `SettingsPlugin`, the RQt plugin around such a widget |
| `typing.py` | `resolve_subclass_args()`, a helper to get TypeVars into class variables |

## The settings of a plugin

A settings class is a dataclass extending `SettingsBase` whose members are `SettingsField`s:

```python
@dataclass
class MissionSettings(SettingsBase):
    service_name: str = TextField(
        '/mission/start', 'Service', 'The service to call when the button is pressed.', 'Service',
        allow_empty=False)
    button_color: Color | None = OptionalColorField(
        None, 'Button color', 'The color of the button. Leave it unset for the standard look.', 'Look')
    confirm_first: bool = BoolField(
        True, 'Ask first', 'Ask whether the mission really should start before the request is sent.', 'Behavior')
```

Every field is given the value to start with, the text of its row in the dialog, the tool tip explaining it, and the
section of the dialog it belongs to (sections for groups with a heading in the dialog). The provided field types are:

| Field | The setting | Asked for as | Stored as |
|---|---|---|---|
| `TextField` | a piece of text | a line edit | the text |
| `BoolField` | a switch | a check box | `True` or `False` |
| `IntField`, `FloatField` | a number, optionally within `limits`, stepped by `step` and written with a `suffix` (a float also with `decimals` places) | a spin box | the number |
| `ChoiceField` | one of a fixed set of values, given as `(value, what it says)` pairs | a combo box | the value |
| `RequiredColorField` | a color the setting has to have | a color button | `Color.name()` |
| `OptionalColorField` | a color the setting can do without, with `clear_tip` saying what "without" means | the same, plus a button to take the color away | the name, or nothing |

Nothing the settings store or the command line brings is ever taken on faith: a number that is not a number or is out
of its limits, a text that is empty where empty is not allowed, and a color that is no color all fall back to the
default of the setting, so a hand-edited perspective cannot break a plugin. The one exception is `OptionalColorField`,
where a value that is missing or unreadable means *no color of my own* rather than the default color.

## Colors

`Color` holds red, green, blue and alpha as plain integers. It is frozen, so it can be the default of a settings
class without one widget's colors leaking into another's, and two colors with the same channels are the same color.
It is written from anything the settings or a message can carry, `Color('#c62828')`, `Color(198, 40, 40)` or
`Color(qcolor)`, and read back with

- `q()` for Qt, `css()` for a style sheet or rich text, `name()` for the short `#rrggbb` form that a color field
  stores, and `lighter()` / `darker()` for the shades a button is painted with,
- `to_color(value, default)` and `to_optional_color(value)`, which never fail: an empty or nonsense color is the
  default, respectively no color, rather than an arbitrary one.

An eight-digit color is read the way Qt reads it, `#aarrggbb`, with the alpha first, which is not the order a CSS
document uses.

## The command line

Every setting has an option named after it, spelled both `--button_color` and `--button-color` because RQt's own
arguments use dashes. A switch is turned on by naming it and takes no value, everything else takes one. The options
are handed to RQt's parser by the launcher of the standalone program, so `--help` lists them together with RQt's own
options:

```python
def main():
    main = Main()
    sys.exit(main.main(sys.argv, standalone='cras_rqt_buttons/EmptyButton',
                       plugin_argument_provider=MissionSettings.add_arguments))
```

What the command line asks for wins over what the perspective stored, and `SettingsBase.from_args()` reports which
settings it did ask for, so a plugin applies those and only those.

## The dialog, the widget and the plugin

`SettingsDialog` builds a row for every setting of the settings class it is given, in the order they are declared and
under a heading for each section. A subclass reaches the widgets through `widget()` and `widgets_of()` in `setup()`,
e.g. to gray out the settings of one section while they mean nothing, and can leave settings out altogether with
`hidden()`; a setting that is not shown keeps the value it was opened with, so hiding is not resetting.

`SettingsWidget` and `SettingsPlugin` say what they work with as the parameters of their class rather than by
overriding anything:

```python
class MissionWidget(SettingsWidget[MissionSettings, SettingsDialog]):
    ...


class CrasRqtMissionButton(SettingsPlugin[MissionWidget]):
    def __init__(self, context, plugin_name: str = 'MissionButton'):
        super().__init__(context, plugin_name)
```

The widget then opens the dialog for the settings it holds, stores what the user agreed to in the settings of RQt and
loads them back next time; a subclass names its window with `window_title`, and rethinks `dialog_title()` if the
dialog for it says anything else than `<window> configuration`. The plugin puts the widget into the RQt window, adds
the number of the instance to its title when there are several of them, hands `shutdown()`, `save_settings()` and
`restore_settings()` to the widget, and opens the dialog when RQt asks the plugin to configure itself. What a plugin
has to add itself is what the widget does, and nothing else.

## Tests

`test/test_common.py` covers the color helpers, each field type reading a stored or given value and writing itself
back, the widgets of the fields round-tripping their value, and the dialog, the widget and the settings of a small
settings class of its own. Like the tests of the plugins, they run inside the ROS 2 environment:

```
colcon test --packages-select cras_rqt_common && colcon test-result --verbose
```

or directly, with the workspace sourced and no display around:

```
QT_QPA_PLATFORM=offscreen python3 -m pytest cras_rqt_common/test
```
