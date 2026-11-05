# cras_rqt_ptz_control

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

A minimalistic RQt plugin for steering a PTZ gimbal-camera, operable by a finger on a touchscreen: it occupies
roughly 190 x 190 px and its buttons are 56 px large. A short tap on one of the four direction buttons or on the
zoom in/out buttons requests one relative motion by a configured step, while holding it (with a mouse or with a
finger) sends velocity commands at a configured rate (10 Hz by default) until the button is released. The center
button asks the gimbal to re-center through a service. Nothing ever waits for an answer – the service call is
issued asynchronously, so the GUI stays responsive and the motion commands keep flowing. The plugin deliberately
shows no gimbal pose; the only feedback is the zoom level, read from a topic of `std_msgs/Float32`, which stays
blank for as long as no values are available.

Commands are sent as `geometry_msgs/TwistStamped` messages where `twist.angular.y` is the pitch,
`twist.angular.z` the yaw (both in radians, or radians per second, respectively) and `twist.linear.x` the zoom
change (zoom levels, or zoom levels per second). The defaults point at
[`cmd_vel_to_gimbal`](../../../../drivers2/src/cras_siyi_driver/nodes/cmd_vel_to_gimbal) of the
[cras_siyi_driver](http://github.com/CRAS-USR/cras_siyi_driver) stack, which translates such commands to the
SiYi gimbals, interprets the zoom command and clamps it to the zoom levels the camera supports, and which
publishes the resulting zoom level on `siyi/zoom`. The widget itself knows nothing about the zoom range – it
only ever asks for relative changes.

Start the plugin either by picking *Plugins &rarr; Robot Tools &rarr; PTZ Control* inside RQt, or standalone by
calling `ros2 run cras_rqt_ptz_control cras_rqt_ptz_control`. The configuration, opened by a gear button in the
dock title bar or in the widget corner, offers the two command topics, the zoom topic, the centering service and
the tilt and zoom steps, rates, command rate and the delay below which a press still counts as a tap; it is
stored in the standard RQt settings and restored next time (when RQt does not offer a freshly built plugin,
let it scan the plugins again by `rqt_gui --force-discover`). To build the package, run
`./build.sh --packages-select cras_rqt_ptz_control` in the root of this workspace.
