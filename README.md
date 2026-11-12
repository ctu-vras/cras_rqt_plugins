# RQt plugins for CRAS robots

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

This package holds RQt plugins that are not part of the ROS distribution. It currently contains

- `cras_rqt_ptz_control`: a touch-friendly D-pad to steer a PTZ gimbal-camera by relative motions and velocities.
- `cras_rqt_text`: a widget showing a text coming from a `std_msgs/String` or `rviz_2d_overlay_msgs/OverlayText`
  topic, with the markup in the text interpreted.
- `cras_rqt_buttons`: large touch-friendly buttons calling `std_srvs/Trigger` and `std_srvs/SetBool` services,
  e.g. `Patrol`, `Home`, `Speak` and `Stop` to control a robot mission.

To build this package, source your ROS 2 distribution and then call

```
colcon build --packages-select cras_rqt_ptz_control
```

in the root of your workspace (the folder that contains the `src` directory). Name the plugin you are
interested in instead of `cras_rqt_ptz_control` to build only that one.
