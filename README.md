# RQt plugins for CRAS robots

<!--
SPDX-License-Identifier: BSD-3-Clause
SPDX-FileCopyrightText: Czech Technical University in Prague
-->

This package holds RQt plugins that are not part of the ROS distribution. It currently contains

- `cras_rqt_ptz_control`: a touch-friendly D-pad to steer a PTZ gimbal-camera by relative motions and velocities.

To build this package, source your ROS 2 distribution and then call

```
./build.sh --packages-select cras_rqt_ptz_control
```

in the root of the `common2` workspace (the folder that contains this `src` directory).
