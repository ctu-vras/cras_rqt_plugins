# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable topics and command amplitudes of the PTZ control plugin."""

from dataclasses import dataclass, field
from typing import Tuple

from cras_rqt_common.settings import SettingsBase


def _topic(label: str, description: str) -> dict:
    """Metadata of a setting with a topic or service name."""
    return {'label': label, 'description': description, 'section': 'Topics'}


def _number(label: str, description: str, suffix: str, decimals: int,
            limits: Tuple[float, float], step: float) -> dict:
    """Metadata of a numeric setting."""
    return {'label': label, 'description': description, 'section': 'Commands', 'suffix': suffix,
            'decimals': decimals, 'limits': limits, 'step': step}


@dataclass
class PtzControlSettings(SettingsBase):
    """Everything the PTZ control plugin can be told to do differently."""

    velocity_topic: str = field(default='siyi/cmd/cmd_vel', metadata=_topic(
        'Velocity topic', 'geometry_msgs/TwistStamped topic for the commanded rates.'))
    relative_topic: str = field(default='siyi/cmd/cmd_pos_rel', metadata=_topic(
        'Relative position topic',
        'geometry_msgs/TwistStamped topic for the commanded relative motions.'))
    zoom_topic: str = field(default='siyi/zoom', metadata=_topic(
        'Zoom topic', 'std_msgs/Float32 topic with the current zoom level. The zoom stays blank '
        'when nothing is published there.'))
    center_service: str = field(default='siyi/cmd/center', metadata=_topic(
        'Center service', 'std_srvs/Trigger service that centers the gimbal when the center '
        'button is pressed. Point it to a non-existing service if you do not have one.'))

    angle_step_deg: float = field(default=15.0, metadata=_number(
        'Tilt step', 'How much to rotate the gimbal when a direction button is tapped.', ' °', 2,
        (0.1, 180.0), 0.5))
    angle_rate_deg_per_s: float = field(default=20.0, metadata=_number(
        'Tilt rate', 'How fast to rotate the gimbal while a direction button is held.', ' °/s', 2,
        (0.1, 90.0), 0.5))
    zoom_step: float = field(default=0.5, metadata=_number(
        'Zoom step', 'How many zoom levels to add when a zoom button is tapped.', ' ×', 2,
        (0.01, 10.0), 0.1))
    zoom_rate_per_s: float = field(default=1.0, metadata=_number(
        'Zoom rate', 'How many zoom levels to add per second while a zoom button is held.',
        ' ×/s', 2, (0.01, 20.0), 0.1))
    command_rate_hz: float = field(default=10.0, metadata=_number(
        'Command rate', 'Frequency of the velocity commands sent while a button is held.',
        ' Hz', 1, (1.0, 100.0), 1.0))
    hold_delay_ms: int = field(default=250, metadata=_number(
        'Hold delay', 'For how long a button must be pressed to be considered held rather than '
        'tapped.', ' ms', 0, (50, 2000), 50))
