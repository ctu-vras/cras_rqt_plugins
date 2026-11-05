# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Configurable topics and command amplitudes of the PTZ control plugin."""

from dataclasses import dataclass, field, fields
from typing import Any, Tuple


def _topic(label: str, description: str) -> dict:
    """Metadata of a setting with a topic or service name."""
    return {'label': label, 'description': description, 'section': 'Topics'}


def _number(label: str, description: str, suffix: str, decimals: int,
            limits: Tuple[float, float], step: float) -> dict:
    """Metadata of a numeric setting."""
    return {'label': label, 'description': description, 'section': 'Commands', 'suffix': suffix,
            'decimals': decimals, 'limits': limits, 'step': step}


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _to_number(value: Any, default, limits: Tuple[float, float], cast):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return default
    return cast(min(max(number, limits[0]), limits[1]))


def _to_name(value: Any, default: str) -> str:
    if value is None:
        return default
    name = str(value).strip()
    return name if name else default


@dataclass
class PtzControlSettings:
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

    def save(self, settings) -> None:
        """Store all values in the given rqt settings proxy."""
        for item in fields(self):
            settings.set_value(item.name, getattr(self, item.name))

    @classmethod
    def load(cls, settings) -> 'PtzControlSettings':
        """
        Load all values from the given rqt settings proxy.

        Unknown, empty or malformed values are silently replaced by the defaults.
        """
        defaults = cls()
        values = {}
        for item in fields(cls):
            default = getattr(defaults, item.name)
            raw = settings.value(item.name, default)
            if item.type is bool:
                values[item.name] = _to_bool(raw, default)
            elif item.type is int:
                values[item.name] = _to_number(raw, default, item.metadata['limits'], int)
            elif item.type is float:
                values[item.name] = _to_number(raw, default, item.metadata['limits'], float)
            else:
                values[item.name] = _to_name(raw, default)
        return cls(**values)
