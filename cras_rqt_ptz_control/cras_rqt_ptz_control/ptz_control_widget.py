# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""The GUI of the PTZ control plugin."""

import math

from cras_rqt_common.settings_dialog import SettingsDialog
from cras_rqt_common.settings_widget import SettingsWidget
from cras_rqt_ptz_control.hold_button import HoldButton
from cras_rqt_ptz_control.ptz_command import PtzCommand
from cras_rqt_ptz_control.ptz_command_engine import PtzCommandEngine
from cras_rqt_ptz_control.ptz_control_settings import PtzControlSettings
from python_qt_binding.QtCore import Qt
from python_qt_binding.QtWidgets import QGridLayout, QLabel, QSizePolicy

TAP_AND_HOLD = ' Tap it to move by one step, hold it to move continuously.'


class PtzControlWidget(SettingsWidget[PtzControlSettings, SettingsDialog]):
    """
    A minimalistic D-pad-like control of a PTZ gimbal-camera.

    The four direction and two zoom buttons request a relative motion when tapped, and velocity
    commands at a configurable (10 Hz by default) rate while held. The center button asks for
    recentering the gimbal, the small gear button opens the configuration. The only feedback is the
    zoom level read from the configured topic; the widget works even without any such messages.
    """

    BUTTON_SIZE = 56  # px, so that the buttons are easy to hit with a finger on a 14" touchscreen
    ZOOM_UNKNOWN = '–'
    BUTTON_NAMES = ('up', 'down', 'left', 'right', 'zoom_in', 'zoom_out', 'center')
    """the buttons the D-pad is made of, by the names the widget uses for them"""

    def __init__(self, node, parent=None):
        super().__init__(parent, 'PTZ Control')
        self.setObjectName('cras_rqt_ptz_control__PtzControl')
        self._commands = {}
        self._engine = PtzCommandEngine(node, self)
        self._engine.zoom_updated.connect(self._show_zoom)

        self._zoom_label = QLabel(self.ZOOM_UNKNOWN, self)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_font = self._zoom_label.font()
        zoom_font.setPointSize(max(16, zoom_font.pointSize() - 1))
        self._zoom_label.setFont(zoom_font)

        self._zoom_out = self._make_button('−', 'Zoom out.' + TAP_AND_HOLD)
        self._up = self._make_button('▲', 'Tilt up.' + TAP_AND_HOLD)
        self._zoom_in = self._make_button('+', 'Zoom in.' + TAP_AND_HOLD)
        self._left = self._make_button('◀', 'Turn the camera to the left.' + TAP_AND_HOLD)
        self._center = self._make_button('⌂', 'Center the gimbal.', tap=self._engine.send_center)
        self._right = self._make_button('▶', 'Turn the camera to the right.' + TAP_AND_HOLD)
        self._down = self._make_button('▼', 'Tilt down.' + TAP_AND_HOLD)

        layout = QGridLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self._zoom_out, 0, 0)
        layout.addWidget(self._up, 0, 1)
        layout.addWidget(self._zoom_in, 0, 2)
        layout.addWidget(self._left, 1, 0)
        layout.addWidget(self._center, 1, 1)
        layout.addWidget(self._right, 1, 2)
        layout.addWidget(self._down, 2, 1)
        layout.addWidget(self._zoom_label, 2, 0, Qt.AlignmentFlag.AlignCenter)

        self.apply_settings(self._settings)

    def pad_button(self, name: str) -> HoldButton:
        """The button of the D-pad with the given name, e.g. ``up`` or ``zoom_in``."""
        return getattr(self, f'_{name}')

    def commands(self) -> dict:
        """
        The motion every button of the D-pad asks for, by the name of the button.

        A button that is tapped asks for a step, and a button that is held asks for a rate; the
        center button asks for neither, it only asks for the gimbal to center itself.
        """
        return {name: self._commands[self.pad_button(name)] for name in self.BUTTON_NAMES
                if self.pad_button(name) in self._commands}

    def zoom(self) -> str:
        """What the widget says about the zoom level of the gimbal right now."""
        return self._zoom_label.text()

    def shutdown(self) -> None:
        """Stop commanding and release the ROS interfaces."""
        self._engine.shutdown()

    def hideEvent(self, event):
        # Nobody is watching the buttons anymore, so do not keep sending velocity commands.
        self._engine.stop_all()
        super().hideEvent(event)

    def _make_button(self, text: str, tip: str, tap=None) -> HoldButton:
        """
        Create a button that reacts both to a tap and to a long press.

        :param tap: what to call on a tap; a step command is sent when it is not given.
        """
        button = HoldButton(text, self)
        button.setToolTip(tip)
        button.setMinimumSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        font = button.font()
        font.setPointSize(font.pointSize() + 16)
        button.setFont(font)
        if tap is not None:
            button.tapped.connect(tap)
            return button
        button.tapped.connect(lambda: self._send_step(button))
        button.hold_started.connect(lambda: self._start_hold(button))
        button.hold_finished.connect(lambda: self._stop_hold(button))
        return button

    def _send_step(self, button) -> None:
        command, _ = self._commands[button]
        self._engine.send_step(command)

    def _start_hold(self, button) -> None:
        _, command = self._commands[button]
        self._engine.start_hold(button, command)

    def _stop_hold(self, button) -> None:
        self._engine.stop_hold(button)

    def apply_settings(self, settings: PtzControlSettings) -> None:
        super().apply_settings(settings)
        step = math.radians(settings.angle_step_deg)
        rate = math.radians(settings.angle_rate_deg_per_s)
        zoom_step = settings.zoom_step
        zoom_rate = settings.zoom_rate_per_s
        self._commands = {
            self._up: (PtzCommand(pitch=-step), PtzCommand(pitch=-rate)),
            self._down: (PtzCommand(pitch=step), PtzCommand(pitch=rate)),
            self._left: (PtzCommand(yaw=step), PtzCommand(yaw=rate)),
            self._right: (PtzCommand(yaw=-step), PtzCommand(yaw=-rate)),
            self._zoom_in: (PtzCommand(zoom=zoom_step), PtzCommand(zoom=zoom_rate)),
            self._zoom_out: (PtzCommand(zoom=-zoom_step), PtzCommand(zoom=-zoom_rate)),
        }
        for button in self._commands:
            button.set_hold_delay(settings.hold_delay_ms)
        self._center.setToolTip('Center the gimbal.')
        self._zoom_label.setToolTip('Zoom level of the gimbal.')
        self._engine.configure(settings)

    def _show_zoom(self, zoom: float) -> None:
        self._zoom_label.setText(f'{zoom:.1f}×')
