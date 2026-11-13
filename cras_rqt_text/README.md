# cras_rqt_text

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

An RQt plugin showing a text coming from a ROS topic. It subscribes either to `std_msgs/String` or to
`rviz_2d_overlay_msgs/OverlayText`, and it shows the text as rich text, so the HTML markup both message types can
carry is interpreted: `<b>bold</b>`, `<i>italic</i>`, `<u>underlined</u>`, `<font color="#ff0000"
size="24">red and big</font>`, `<span style="color: lime">CSS colors</span>`, `<br/>` and paragraphs all come out
the way their sender meant them. That is also what
[the overlay text display of rviz_2d_overlay_plugins](https://github.com/teamspatzenhirn/rviz_2d_overlay_plugins)
paints in RViz, so Qt's rich text subset applies here too: consecutive spaces collapse, the text wraps when it does
not fit the widget, and only angle brackets that cannot start a tag, such as the one in `3 < 5`, are escaped so that
they do not vanish.

## Configuration

| Setting                          | Meaning                                                                                |
|----------------------------------|----------------------------------------------------------------------------------------|
| `topic`                          | the topic to listen on; empty to only show the default text                              |
| `message_type`                   | `std_msgs/msg/String` or `rviz_2d_overlay_msgs/msg/OverlayText`                          |
| `default_text`                   | what to show until the first message arrives                                             |
| `text_size_pt`                   | how tall the text is, in points                                                          |
| `scale_with_widget`              | whether the text grows and shrinks with the widget instead of staying the same tall      |
| `reference_height`               | the widget height the text size above holds for, when the text scales                    |
| `text_color`                     | the color of the text; empty for the color rqt writes its own text with                  |
| `background_color`               | the color the widget is filled with; empty for the background of any widget              |
| `horizontal_alignment`           | where the text sits in the widget, from the left, from the centre or from the right       |
| `vertical_alignment`             | the same vertically, from the top, from the centre or from the bottom                     |
| `take_style_from_message`        | whether an OverlayText message may pick its own size, font and text color                 |
| `take_background_from_message`   | whether an OverlayText message may pick its own background color                           |
| `take_layout_from_message`       | whether an OverlayText message may pick its own alignment, distances and size             |

Both colors default to the colors any other rqt widget has, taken from its palette, so a freshly opened plugin looks
like the rest of rqt and follows its light or dark theme. The configuration dialog shows that color on the button and
offers a *Standard* button to get back to it. An explicit color can be written as `#ff000080`
(the first two digits being the alpha). Empty `topic` is a valid setting: the plugin then just shows the default text.

Until the first message arrives, the widget shows the default text with the configured appearance, so that a freshly
opened plugin does not look broken. An OverlayText message brings its own appearance and position along, and the
three `take_*` settings say which of it to obey and which of it to override by what is configured above; a `String`
message has nothing of its own, so it is always shown with the configured appearance. As in the RViz display, a
message with `action` set to `DELETE` hides the text, and `ADD` is treated the same as `OVERWRITE`, i.e. every
message replaces the whole text.

The subscription asks for the reliability and durability the publishers on the topic offer, so a text published as
best effort is heard and a latched one that was published before RQt started is shown right away; until there is
nothing to copy, the system default is used. When the topic is published with a different message type than the one
configured, the plugin says so in the log, because nothing else would ever show up.

## Running it

Start the plugin by picking *Plugins &rarr; Visualization &rarr; Text* inside RQt, or on its own by

```
ros2 run cras_rqt_text cras_rqt_text
```

and show something on the topic it listens to by default:

```
ros2 topic pub --once /overlay_text std_msgs/msg/String "{data: 'battery <font color=\"#ff0000\">low</font>'}"
```

The settings live in the perspective RQt stores, and are changed in the RQt configuration dialog, opened by the gear
button in the dock of the plugin. Several instances can be open at once, each with its own topic and appearance.
