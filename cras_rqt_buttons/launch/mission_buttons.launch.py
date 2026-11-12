# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""A set of buttons to control a robot mission: Patrol, Home, Speak and Stop."""

from launch import LaunchDescription
from launch_ros.actions import Node

MISSION_NAMESPACE = '/mission'

#: what the four buttons of the mission control look like and which service they call
BUTTONS = (
    dict(executable='trigger_button', service='patrol', text='Patrol',
         color='#2e7d32', text_color='#ffffff'),
    dict(executable='trigger_button', service='home', text='Home',
         color='#4a90d9', text_color='#ffffff'),
    dict(executable='push_button', service='speak', text='Speak',
         color='#f9a825', text_color='#000000'),
    dict(executable='trigger_button', service='stop', text='Stop',
         color='#c62828', text_color='#ffffff'),
)


def button_arguments(button) -> list:
    """The command line asking the plugin for one button of the mission control."""
    return [
        '--service_name', f'{MISSION_NAMESPACE}/{button["service"]}',
        '--button_text', button['text'],
        '--button_color', button['color'],
        '--text_color', button['text_color'],
    ]


def generate_launch_description():
    """Start one window per button, each of them calling its own service."""
    buttons = [
        Node(
            package='cras_rqt_buttons',
            executable=button['executable'],
            output='screen',
            arguments=button_arguments(button),
        )
        for button in BUTTONS
    ]
    return LaunchDescription(buttons)
