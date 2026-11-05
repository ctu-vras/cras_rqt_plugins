# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""A single gimbal-camera command."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PtzCommand:
    """
    A request to move the gimbal-camera.

    Depending on the command type, the numbers are either amplitudes of a relative motion
    (radians, zoom levels), or rates (radians per second, zoom levels per second).
    """

    pitch: float = 0.0
    yaw: float = 0.0
    zoom: float = 0.0
