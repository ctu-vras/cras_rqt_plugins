# cras_rqt_buttons

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

Two RQt plugins, each of them a single large button that calls a ROS service. They are meant for the kind of
control an operator does with a finger on a touchscreen, or in a hurry: the button is at least 120 x 120 px, it
has no focus frame to distract from it, and its text is made as large as the space the button has, so it stays
readable when the button is docked small and becomes a sign you can read from a distance when the button fills
the screen. Touches are turned into clicks by Qt itself, so a finger, a stylus and a mouse button all do the same
thing.

`CrasRqtTriggerButton` calls a `std_srvs/srv/Trigger` service when the button is clicked. `CrasRqtPushButton`
calls a `std_srvs/srv/SetBool` service with `true` when the button is pressed and with `false` when it is
released, which is what a push-to-talk button on a robot needs; with `invert_value` it sends the other way
round, so `false` while the button is held and `true` once it is let go. A button that is released by closing or
hiding its dock still sends the request that belongs to the release, so nothing is left running because the
window disappeared under the finger.

Nothing waits for a service or for a response. The button is disabled until the configured service is found, and
it becomes disabled again if the service goes away; the request itself is handed to rclpy asynchronously and the
answer is reported through a signal, so the GUI never freezes, not even when the service takes half a minute to
answer. When a call fails, the button turns **red** and says what happened in its tooltip; it stops being red as
soon as it is pressed again. A call counts as failed when the service refuses it (`success` being `false`), when
it cannot be sent at all, or when it does not answer within the configurable response timeout. For the push
button, only the outcome of the request that is the valid one now is shown: if the service is slow to answer the
press and the button is released in the meantime, the outcome of the release is what the button shows.

## Configuration

Every button takes these settings, whatever the way they are given to it:

| Setting            | Meaning                                                                              |
|--------------------|--------------------------------------------------------------------------------------|
| `service_name`     | the service to call; relative names are taken from the root of the graph             |
| `button_text`      | what the button says, empty text allowed                                             |
| `button_color`     | the color of the button while it is ready to be pressed, empty for the standard look |
| `text_color`       | the color of the text on the button, empty for the color the Qt style uses           |
| `error_color`      | the color of the button once a call fails                                            |
| `response_timeout` | after how long a call without an answer counts as failed, 0 to wait forever          |
| `invert_value`     | for the push button: send `false` while held and `true` once released                |

By default the buttons are not painted at all, so they look like any other Qt button and follow the Qt theme in
use. Give `button_color` (and optionally `text_color`) a color and the button is painted with it, with a darker
border, a pressed shade and a faded-out look while it is disabled; take the color away again and the standard look
comes back. `error_color` always has a color, because a failed call is meant to be impossible to miss. The colors
are anything `QColor` understands, so `red`, `#c62828` and `#c6282880` all work. The settings can be changed in
three ways, and what is given on the command line wins over what was stored before:

- the RQt configuration dialog, opened by *Configure* in the plugin dock (or by the corresponding entry in the
  RQt plugins menu). Every color is one field showing a chip of the color next to its hex value, and clicking it
  opens a color picker; the `×` button next to the field takes the color away again, so that the button is painted
  the way an ordinary Qt button is, and it can only be pressed while there is a color to take away. The color of a
  failed call has no `×`, because it is not meant to be turned off,
- the settings RQt stores with the perspective, so the buttons come back as they were left,
- the command line, with options named after the settings in both spellings, e.g.
  `--service_name /mission/patrol --button-text Patrol --button-color '#2e7d32'`. A switch such as
  `invert_value` does not need a value of its own, so `--invert-value` turns it on and `--invert-value false`
  turns it off.

## Controlling a robot mission

Four instances of these plugins make the mission control of the issue: `Patrol`, `Home` and `Stop` as trigger
buttons calling `/mission/patrol`, `/mission/home` and `/mission/stop`, and `Speak` as a push button calling
`/mission/speak` with `true` while it is held. `ros2 launch cras_rqt_buttons mission_buttons.launch.py` starts a
window with these four buttons, configured through the command-line options, so it can be used as it is or taken
as an example. To have all four in a single window, start `rqt_gui` and load *Plugins &rarr; Robot Tools &rarr;
Mission Trigger Button* (three times) and *Mission Push Button*, then configure each of them; RQt remembers the
buttons and their settings in the perspective. A single button can also be started on its own, e.g.

```
ros2 run cras_rqt_buttons trigger_button --service_name /mission/stop --button_text Stop
ros2 run cras_rqt_buttons push_button --service_name /mission/speak --button_text Speak
ros2 run cras_rqt_buttons push_button --service_name /mission/siren --invert-value
```

Note that the plugins share the RQt node, whose name is `rqt_gui_py_node_<pid>`, so a service name starting with
`~` lands in that namespace; an absolute name such as `/mission/patrol` or a plain name such as `patrol` is what
a mission server will normally offer.

## Building and testing

Build the package by `./build.sh --packages-select cras_rqt_buttons` in the root of the `common2` workspace (the
folder that contains this `src` directory). RQt caches the plugins it has found, so after a fresh build let it
look again by `rqt_gui --force-discover`. The tests drive the buttons, the settings and the launch file against
real ROS services and can be run by `python3 -m pytest test/test_buttons.py` in this folder, with the workspace
and a ROS 2 distribution sourced.
