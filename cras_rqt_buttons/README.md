# cras_rqt_buttons

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

RQt buttons that call a ROS service.

`CrasRqtTriggerButton` calls a `std_srvs/srv/Trigger` service when the button is clicked.
`CrasRqtEmptyButton` calls a `std_srvs/srv/Empty` service when the button is clicked.
`CrasRqtPushButton` calls a `std_srvs/srv/SetBool` service with `true` when the button is pressed and with `false`
when it is release (with `invert_value` it sends the other way round). A button that is released by closing or
hiding its dock still sends the request that belongs to the release.

Nothing waits for a service or for a response. The button is disabled until the configured service is found, and
it becomes disabled again if the service goes away; the request itself is handed to rclpy asynchronously and the
answer is reported through a signal, so the GUI never freezes, not even when the service takes half a minute to
answer. When a call fails, the button turns **red** and says what happened in its tooltip; it stops being red as
soon as it is pressed again. A call counts as failed when the service refuses it (`success` being `false`), when
it cannot be sent at all, or when it does not answer within the configurable response timeout. For the push
button, only the outcome of the request that is the valid one now is shown: if the service is slow to answer the
press and the button is released in the meantime, the outcome of the release is what the button shows.

## Configuration

Every button takes these settings:

| Setting            | Meaning                                                                              |
|--------------------|--------------------------------------------------------------------------------------|
| `service_name`     | the service to call; relative names are resolved by node namespace             |
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

- the RQt configuration dialog, opened by *Configure* in the plugin dock,
- the settings RQt stores with the perspective, so the buttons come back as they were left,
- the command line, with options named after the settings in both spellings, e.g.
  `--service_name /mission/patrol --button-text Patrol --button-color '#2e7d32'`. A switch such as
  `invert_value` does not need a value of its own, so `--invert-value` turns it on and `--invert-value false`
  turns it off.
