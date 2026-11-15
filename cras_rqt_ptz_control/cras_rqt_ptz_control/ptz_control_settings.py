# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable topics and command amplitudes of the PTZ control plugin."""

from dataclasses import dataclass

from cras_rqt_common.settings import SettingsBase
from cras_rqt_common.settings_fields import FloatField, IntField, TextField

SEC_TOPICS = 'Topics'
SEC_COMMANDS = 'Commands'


@dataclass
class PtzControlSettings(SettingsBase):
    """Everything the PTZ control plugin can be told to do differently."""

    velocity_topic: str = TextField(  # type: ignore[bad-assignment]
        'siyi/cmd/cmd_vel', 'Velocity topic',
        'geometry_msgs/TwistStamped topic for the commanded rates.', SEC_TOPICS)
    relative_topic: str = TextField(  # type: ignore[bad-assignment]
        'siyi/cmd/cmd_pos_rel', 'Relative position topic',
        'geometry_msgs/TwistStamped topic for the commanded relative motions.', SEC_TOPICS)
    zoom_topic: str = TextField(  # type: ignore[bad-assignment]
        'siyi/zoom', 'Zoom topic',
        'std_msgs/Float32 topic with the current zoom level. The zoom stays blank when nothing is '
        'published there.', SEC_TOPICS)
    center_service: str = TextField(  # type: ignore[bad-assignment]
        'siyi/cmd/center', 'Center service',
        'std_srvs/Trigger service that centers the gimbal when the center button is pressed. Point '
        'it to a non-existing service if you do not have one.', SEC_TOPICS)

    angle_step_deg: float = FloatField(  # type: ignore[bad-assignment]
        15.0, 'Tilt step', 'How much to rotate the gimbal when a direction button is tapped.', SEC_COMMANDS,
        limits=(0.1, 180.0), step=0.5, suffix=' °')
    angle_rate_deg_per_s: float = FloatField(  # type: ignore[bad-assignment]
        20.0, 'Tilt rate', 'How fast to rotate the gimbal while a direction button is held.', SEC_COMMANDS,
        limits=(0.1, 90.0), step=0.5, suffix=' °/s')
    zoom_step: float = FloatField(  # type: ignore[bad-assignment]
        0.5, 'Zoom step', 'How many zoom levels to add when a zoom button is tapped.', SEC_COMMANDS,
        limits=(0.01, 10.0), step=0.1, suffix=' ×')
    zoom_rate_per_s: float = FloatField(  # type: ignore[bad-assignment]
        1.0, 'Zoom rate', 'How many zoom levels to add per second while a zoom button is held.', SEC_COMMANDS,
        limits=(0.01, 20.0), step=0.1, suffix=' ×/s')
    command_rate_hz: float = FloatField(  # type: ignore[bad-assignment]
        10.0, 'Command rate', 'Frequency of the velocity commands sent while a button is held.', SEC_COMMANDS,
        limits=(1.0, 100.0), step=1.0, suffix=' Hz', decimals=1)
    hold_delay_ms: int = IntField(  # type: ignore[bad-assignment]
        250, 'Hold delay', 'For how long a button must be pressed to be held rather than tapped.', SEC_COMMANDS,
        limits=(50, 2000), step=50, suffix=' ms')
