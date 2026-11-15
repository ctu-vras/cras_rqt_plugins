# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Tests of the PTZ control plugin."""

import math
import os
import time
import unittest
from dataclasses import fields

from cras_rqt_common.settings_dialog import SettingsDialog

# The tests build real widgets but we don't want to show them when running on a machine with a display.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import rclpy  # noqa: E402
from cras_rqt_ptz_control.hold_button import HoldButton  # noqa: E402
from cras_rqt_ptz_control.ptz_command import PtzCommand  # noqa: E402
from cras_rqt_ptz_control.ptz_command_engine import PtzCommandEngine  # noqa: E402
from cras_rqt_ptz_control.ptz_control import PtzControl  # noqa: E402
from cras_rqt_ptz_control.ptz_control_settings import PtzControlSettings  # noqa: E402
from cras_rqt_ptz_control.ptz_control_widget import PtzControlWidget  # noqa: E402
from geometry_msgs.msg import TwistStamped  # noqa: E402
from python_qt_binding.QtCore import QEvent, QObject, Qt  # noqa: E402
from python_qt_binding.QtGui import QMouseEvent  # noqa: E402
from python_qt_binding.QtWidgets import QApplication  # noqa: E402
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import QoSProfile  # noqa: E402
from std_msgs.msg import Float32, String  # noqa: E402
from std_srvs.srv import Trigger  # noqa: E402

try:
    # Qt6
    from python_qt_binding.QtCore import QPointF
except AttributeError:
    # Qt5
    from python_qt_binding.QtCore import QPoint
    QPointF = QPoint

DEPTH = QoSProfile(depth=100)


class SettingsProxy:
    """A stand-in for the settings proxy rqt hands to the plugins."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, name, default=None):
        return self.values.get(name, default)

    def set_value(self, name, value):
        self.values[name] = value


class GuiTest(unittest.TestCase):
    """A test that builds widgets, without ever showing them on a screen."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])


class RosGuiTest(GuiTest):
    """
    A node the widgets and the engines talk through, spun by hand.

    Spinning the node and processing the GUI events happen in the same loop, so nothing runs in
    parallel and the tests see exactly what the operator would see at the given moment.
    """

    @classmethod
    def setUpClass(cls):
        if not rclpy.ok():
            rclpy.init()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = Node('ptz_control_tests')
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.widgets = []
        self.engines = []
        self.extra_nodes = []

    def tearDown(self):
        for widget in self.widgets:
            widget.shutdown()
            widget.deleteLater()
        for engine in self.engines:
            engine.shutdown()
        for node in self.extra_nodes:
            node.destroy_node()
        self.executor.remove_node(self.node)
        self.node.destroy_node()

    # helpers

    def spin(self, duration: float = 0.0) -> None:
        """Let the node and the GUI handle whatever is pending, without waiting in parallel."""
        deadline = time.monotonic() + duration
        while True:
            self.executor.spin_once(timeout_sec=0.0)
            self.app.processEvents()
            if time.monotonic() >= deadline:
                return

    def spin_until(self, condition, timeout: float = 5.0) -> bool:
        """Spin until the condition holds, and tell whether it ever did."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            self.executor.spin_once(timeout_sec=0.02)
            self.app.processEvents()
        return bool(condition())

    def make_engine(self, **settings) -> PtzCommandEngine:
        """An engine talking through the node of the test, configured as the settings say."""
        engine = PtzCommandEngine(self.node)
        self.engines.append(engine)
        engine.configure(PtzControlSettings(**settings))
        return engine

    def watch(self, topic: str, message_type=TwistStamped) -> list:
        """
        Collect what arrives on a topic, in the order it arrives.

        The returned list grows while the test spins, so a test can look at it whenever it likes.
        """
        seen = []
        self.node.create_subscription(message_type, topic, lambda msg: seen.append(msg), DEPTH)
        # what is published right after the subscription was made would be lost, so give the
        # discovery of the topic a moment before the test starts sending anything
        self.spin(0.2)
        return seen

    def make_widget(self, **settings) -> PtzControlWidget:
        """A widget talking through the node of the test, configured as the settings say."""
        widget = PtzControlWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(PtzControlSettings(**settings))
        return widget

    def serve(self, name, handler=None, node: Node = None):
        """Offer a centering service; by default from the node of the test, so it is answered."""
        node = node if node is not None else self.node
        if handler is None:
            def handler(request, response):
                response.success = True
                response.message = 'centered'
                return response
        return node.create_service(Trigger, name, handler)

    def press(self, button, for_: float = 0.0) -> None:
        """
        Press a button the way a finger or a mouse would, and keep it pressed.

        :param for_: how long to let the button stay pressed, spinning the node meanwhile
        """
        self._mouse_event(button, QEvent.Type.MouseButtonPress)
        self.spin(for_)

    def release(self, button, for_: float = 0.1) -> None:
        """Let the button go."""
        self._mouse_event(button, QEvent.Type.MouseButtonRelease)
        self.spin(for_)

    def tap(self, button, for_: float = 0.1) -> None:
        """Press and let go of the button, which is what a tap looks like."""
        self.press(button)
        self.release(button, for_=for_)

    def _mouse_event(self, button, event_type) -> None:
        pressed = Qt.MouseButton.LeftButton if event_type == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
        # the button has to be laid out to know where its center is
        button.resize(button.minimumSizeHint())
        event = QMouseEvent(event_type, QPointF(button.rect().center()), Qt.MouseButton.LeftButton, pressed,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(button, event)
        self.app.processEvents()


class HoldButtonTest(RosGuiTest):
    """What a button of the D-pad says about a tap and about a long press."""

    def make_button(self, delay: int = 60) -> HoldButton:
        button = HoldButton('▲')
        button.set_hold_delay(delay)
        self.addCleanup(button.deleteLater)
        return button

    def listen(self, button) -> dict:
        """What the button reported, by the name of the signal."""
        said = {'tapped': 0, 'hold_started': 0, 'hold_finished': 0}
        button.tapped.connect(lambda: said.__setitem__('tapped', said['tapped'] + 1))
        button.hold_started.connect(lambda: said.__setitem__('hold_started', said['hold_started'] + 1))
        button.hold_finished.connect(lambda: said.__setitem__('hold_finished', said['hold_finished'] + 1))
        return said

    def test_a_button_pressed_let_go_of_right_away_has_been_tapped(self):
        button = self.make_button()
        said = self.listen(button)
        self.tap(button)
        self.assertEqual(1, said['tapped'])
        self.assertEqual(0, said['hold_started'])
        self.assertEqual(0, said['hold_finished'])

    def test_a_button_held_says_so_and_says_so_once_it_is_let_go_of(self):
        button = self.make_button()
        said = self.listen(button)
        self.press(button, for_=0.3)  # longer than the 60 ms the button waits before it counts as held
        self.assertEqual(1, said['hold_started'])
        self.assertEqual(0, said['tapped'])  # a hold is not a tap, not even afterwards
        self.assertEqual(0, said['hold_finished'])
        self.release(button)
        self.assertEqual(1, said['hold_finished'])
        self.assertEqual(0, said['tapped'])

    def test_a_button_that_is_pressed_and_released_twice_is_tapped_twice(self):
        button = self.make_button()
        said = self.listen(button)
        self.tap(button)
        self.tap(button)
        self.assertEqual(2, said['tapped'])
        self.assertEqual(0, said['hold_started'])

    def test_a_button_held_and_pressed_again_says_nothing_more(self):
        # e.g. a touch screen that keeps reporting the finger moving over the pressed button
        button = self.make_button()
        said = self.listen(button)
        self.press(button, for_=0.3)
        self._mouse_event(button, QEvent.Type.MouseButtonPress)
        self.spin(0.2)
        self.assertEqual(1, said['hold_started'])
        self.release(button)
        self.assertEqual(1, said['hold_finished'])

    def test_a_press_let_go_of_outside_the_button_neither_taps_nor_holds(self):
        # the finger slid away, so the button is not to blame and should not do anything
        button = self.make_button()
        said = self.listen(button)
        self._mouse_event(button, QEvent.Type.MouseButtonPress)
        event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(-20, -20), Qt.MouseButton.LeftButton,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(button, event)
        self.spin(0.2)
        self.assertEqual({}, {name: count for name, count in said.items() if count})
        self.assertFalse(button.isDown())  # and the button does not stay pressed either

    def test_a_button_can_be_told_to_count_as_held_at_once(self):
        button = self.make_button(delay=0)
        said = self.listen(button)
        self.press(button, for_=0.05)
        self.assertEqual(1, said['hold_started'])
        self.assertEqual(0, said['tapped'])
        self.release(button)


class CommandTest(unittest.TestCase):
    """The command the widget asks for and the engine sends."""

    def test_a_command_that_says_nothing_moves_nothing(self):
        self.assertEqual((0.0, 0.0, 0.0), (PtzCommand().pitch, PtzCommand().yaw, PtzCommand().zoom))

    def test_two_same_commands_are_the_same_command(self):
        # the buttons are keys to the commands they ask for, so a command has to be comparable
        self.assertEqual(PtzCommand(pitch=-1.0), PtzCommand(pitch=-1.0))
        self.assertNotEqual(PtzCommand(pitch=-1.0), PtzCommand(pitch=1.0))
        self.assertEqual(hash(PtzCommand(zoom=2.0)), hash(PtzCommand(zoom=2.0)))
        with self.assertRaises(Exception):
            PtzCommand(pitch=1.0).yaw = 2.0  # a command nobody can change under the engine's hands


class EngineTest(RosGuiTest):
    """What the engine publishes and calls, and when."""

    def test_a_step_is_published_as_a_relative_motion(self):
        sent = self.watch('/ptz_tests/relative')
        engine = self.make_engine(relative_topic='/ptz_tests/relative', velocity_topic='/ptz_tests/velocity')
        engine.send_step(PtzCommand(pitch=-math.radians(15.0), yaw=math.radians(30.0), zoom=0.5))
        self.spin_until(lambda: len(sent) == 1)
        self.assertEqual(1, len(sent), 'nothing was published for the relative motion')
        self.assertAlmostEqual(-math.radians(15.0), sent[0].twist.angular.y)
        self.assertAlmostEqual(math.radians(30.0), sent[0].twist.angular.z)
        self.assertAlmostEqual(0.5, sent[0].twist.linear.x)
        self.assertNotEqual(0, sent[0].header.stamp.sec + sent[0].header.stamp.nanosec)  # it is stamped

    def test_a_step_with_nowhere_to_go_is_simply_not_sent(self):
        engine = self.make_engine(relative_topic='')
        engine.send_step(PtzCommand(pitch=1.0))  # the widget is configured without that topic
        self.spin(0.2)

    def test_a_held_button_sends_velocities_until_it_is_let_go_of(self):
        sent = self.watch('/ptz_tests/held')
        engine = self.make_engine(velocity_topic='/ptz_tests/held', command_rate_hz=40.0)
        engine.start_hold('up', PtzCommand(pitch=-1.0))
        self.assertTrue(self.spin_until(lambda: len(sent) >= 2, timeout=2.0),
                        'the gimbal was not told to keep moving')
        self.assertAlmostEqual(-1.0, sent[0].twist.angular.y)
        engine.stop_hold('up')
        after = len(sent)
        self.assertTrue(self.spin_until(lambda: len(sent) > after))
        last = sent[-1]
        self.assertEqual((0.0, 0.0, 0.0), (last.twist.angular.y, last.twist.angular.z, last.twist.linear.x))
        self.spin(0.4)
        self.assertLessEqual(len(sent), after + 2)  # and now it stops telling it over and over

    def test_two_buttons_held_at_once_move_the_gimbal_both_ways(self):
        sent = self.watch('/ptz_tests/both')
        engine = self.make_engine(velocity_topic='/ptz_tests/both', command_rate_hz=20.0)
        engine.start_hold('up', PtzCommand(pitch=-1.0))
        engine.start_hold('zoom', PtzCommand(zoom=2.0))
        self.assertTrue(self.spin_until(lambda: len(sent) >= 2, timeout=2.0))
        self.assertAlmostEqual(-1.0, sent[-1].twist.angular.y)
        self.assertAlmostEqual(2.0, sent[-1].twist.linear.x)
        # letting one of them go leaves the other one moving, and stops nothing
        engine.stop_hold('up')
        self.assertTrue(self.spin_until(lambda: sent[-1].twist.angular.y == 0.0, timeout=2.0))
        self.assertAlmostEqual(2.0, sent[-1].twist.linear.x)
        engine.stop_all()
        self.assertTrue(self.spin_until(lambda: sent[-1].twist.linear.x == 0.0, timeout=2.0))

    def test_velocities_go_to_the_topic_the_settings_name(self):
        first, second = self.watch('/ptz_tests/velocity_first'), self.watch('/ptz_tests/velocity_second')
        engine = self.make_engine(velocity_topic='/ptz_tests/velocity_first')
        engine.start_hold('up', PtzCommand(pitch=-1.0))
        self.spin_until(lambda: len(first) >= 1)
        engine.configure(PtzControlSettings(velocity_topic='/ptz_tests/velocity_second'))
        self.spin(0.2)  # the held button keeps sending, now somewhere else
        before = len(first)
        self.spin_until(lambda: len(second) >= 2, timeout=2.0)
        self.assertEqual(before, len(first), 'the old topic is still being published to')
        engine.stop_all()

    def test_the_center_service_is_called_when_it_is_there(self):
        calls = []

        def center(request, response):
            calls.append(request)
            response.success = True
            return response

        service = self.serve('/ptz_tests/center', center)
        engine = self.make_engine(center_service='/ptz_tests/center')
        self.assertTrue(self.spin_until(lambda: engine._center_client.service_is_ready()))
        engine.send_center()
        self.assertTrue(self.spin_until(lambda: len(calls) == 1))
        # a second request is not sent while the first one is still on its way, and nobody waits for
        # the answer here, so the widget stays responsive either way
        engine.send_center()
        self.spin(0.3)
        self.assertEqual(1, len(calls))
        self.spin_until(lambda: not engine._center_pending)
        engine.send_center()
        self.assertTrue(self.spin_until(lambda: len(calls) == 2))
        self.node.destroy_service(service)

    def test_a_center_service_that_is_not_there_is_left_alone(self):
        engine = self.make_engine(center_service='/ptz_tests/nowhere')
        engine.send_center()  # the gimbal has no centering service, which is allowed
        self.spin(0.3)

    def test_the_zoom_level_is_told_to_the_widget_as_it_arrives(self):
        levels = []
        engine = self.make_engine(zoom_topic='/ptz_tests/zoom')
        engine.zoom_updated.connect(levels.append)
        publisher = self.node.create_publisher(Float32, '/ptz_tests/zoom', DEPTH)
        self.assertTrue(self.spin_until(lambda: engine._zoom_sub is not None),
                        'the engine never found a message type to listen to')
        publisher.publish(Float32(data=4.5))
        self.assertTrue(self.spin_until(lambda: 4.5 in levels), 'the zoom level never reached the widget')
        # what is not a number has nothing to say about the zoom
        publisher.publish(Float32(data=float('nan')))
        self.spin(0.3)
        self.assertNotIn(float('nan'), levels)
        publisher.publish(Float32(data=9.0))
        self.assertTrue(self.spin_until(lambda: 9.0 in levels))

    def test_a_topic_of_a_type_the_zoom_is_never_published_as_is_ignored(self):
        levels = []
        engine = self.make_engine(zoom_topic='/ptz_tests/not_a_number')
        engine.zoom_updated.connect(levels.append)
        publisher = self.node.create_publisher(String, '/ptz_tests/not_a_number', DEPTH)
        publisher.publish(String(data='4.5'))
        self.spin(1.0)  # long enough for the engine to look for the topic a couple of times
        self.assertIsNone(engine._zoom_sub)
        self.assertEqual([], levels)

    def test_an_engine_that_stopped_sends_nothing_anymore(self):
        sent = self.watch('/ptz_tests/stopping')
        engine = PtzCommandEngine(self.node)
        engine.configure(PtzControlSettings(velocity_topic='/ptz_tests/stopping',
                                            relative_topic='/ptz_tests/stopping'))
        engine.start_hold('up', PtzCommand(pitch=-1.0))
        self.assertTrue(self.spin_until(lambda: len(sent) >= 1), 'the held button sent nothing')
        engine.shutdown()
        after = len(sent)
        engine.start_hold('down', PtzCommand(pitch=1.0))
        engine.send_step(PtzCommand(pitch=1.0))
        engine.stop_all()
        self.spin(0.5)
        self.assertEqual(after, len(sent), 'a stopped engine keeps publishing')


class WidgetTest(RosGuiTest):
    """How the D-pad behaves towards the operator and towards the gimbal."""

    def test_the_d_pad_has_the_buttons_it_promises(self):
        widget = self.make_widget()
        for name in PtzControlWidget.BUTTON_NAMES:
            button = widget.pad_button(name)
            self.assertIsInstance(button, HoldButton)
            self.assertGreaterEqual(button.minimumWidth(), widget.BUTTON_SIZE)
            self.assertTrue(button.toolTip())  # every button says what it does
        # the center button centers, and every other button asks for a motion in both directions
        self.assertEqual({'up', 'down', 'left', 'right', 'zoom_in', 'zoom_out'}, set(widget.commands()))
        self.assertEqual(widget.ZOOM_UNKNOWN, widget.zoom())  # nothing was published to look at yet

    def test_tapping_a_direction_button_asks_for_one_step_of_the_right_size(self):
        sent = self.watch('/ptz_tests/widget_relative')
        widget = self.make_widget(relative_topic='/ptz_tests/widget_relative', angle_step_deg=20.0,
                                  zoom_step=2.0)
        self.tap(widget.pad_button('up'))
        self.assertTrue(self.spin_until(lambda: len(sent) >= 1), 'the gimbal was not asked to move')
        self.assertAlmostEqual(-math.radians(20.0), sent[-1].twist.angular.y)
        self.tap(widget.pad_button('down'))
        self.assertTrue(self.spin_until(lambda: len(sent) >= 2))
        self.assertAlmostEqual(math.radians(20.0), sent[-1].twist.angular.y)
        self.tap(widget.pad_button('zoom_in'))
        self.assertTrue(self.spin_until(lambda: len(sent) >= 3))
        self.assertAlmostEqual(2.0, sent[-1].twist.linear.x)

    def test_holding_a_direction_button_asks_for_a_rate_until_it_is_let_go_of(self):
        held = self.watch('/ptz_tests/widget_velocity')
        widget = self.make_widget(velocity_topic='/ptz_tests/widget_velocity', angle_rate_deg_per_s=30.0,
                                  hold_delay_ms=60, command_rate_hz=30.0)
        self.press(widget.pad_button('left'), for_=0.3)
        self.assertTrue(self.spin_until(lambda: len(held) >= 2), 'holding the button sends nothing')
        self.assertAlmostEqual(math.radians(30.0), held[-1].twist.angular.z)
        self.release(widget.pad_button('left'))
        self.assertTrue(self.spin_until(lambda: held[-1].twist.angular.z == 0.0))

    def test_the_widget_says_what_the_gimbal_tells_it_about_the_zoom(self):
        publisher = self.node.create_publisher(Float32, '/ptz_tests/widget_zoom', DEPTH)
        widget = self.make_widget(zoom_topic='/ptz_tests/widget_zoom')
        self.spin(0.4)  # the widget has to find out what to listen to first
        publisher.publish(Float32(data=3.25))
        self.assertTrue(self.spin_until(lambda: widget.zoom() != widget.ZOOM_UNKNOWN),
                        'the zoom level never reached the widget')
        self.assertIn(widget.zoom(), ('3.2×', '3.3×'))  # what the gimbal says, to one decimal

    def test_a_widget_that_is_hidden_stops_moving_the_gimbal(self):
        held = self.watch('/ptz_tests/widget_hidden')
        widget = self.make_widget(velocity_topic='/ptz_tests/widget_hidden', hold_delay_ms=60,
                                  command_rate_hz=30.0)
        widget.show()
        self.app.processEvents()
        self.press(widget.pad_button('up'), for_=0.3)
        self.assertTrue(self.spin_until(lambda: len(held) >= 1))
        widget.hide()  # the dock with the widget was closed while the button was held
        self.spin(0.3)
        self.assertEqual(0.0, held[-1].twist.angular.y, 'the gimbal keeps moving for a hidden widget')

    def test_the_center_button_calls_the_service_and_only_that_one(self):
        calls = []

        def center(request, response):
            calls.append(request)
            response.success = True
            return response

        service = self.serve('/ptz_tests/widget_center', center)
        relative = self.watch('/ptz_tests/widget_center_relative')
        widget = self.make_widget(center_service='/ptz_tests/widget_center',
                                  relative_topic='/ptz_tests/widget_center_relative')
        self.tap(widget.pad_button('center'))
        self.assertTrue(self.spin_until(lambda: len(calls) == 1), 'centering was not asked for')
        self.assertEqual([], relative)  # and no motion was asked for by the same tap
        self.node.destroy_service(service)

    def test_the_widget_shows_the_settings_it_was_given(self):
        widget = self.make_widget(angle_step_deg=15.0, hold_delay_ms=250, angle_rate_deg_per_s=7.5)
        step, hold = widget.commands()['up']
        self.assertAlmostEqual(-math.radians(15.0), step.pitch)
        self.assertAlmostEqual(-math.radians(7.5), hold.pitch)
        self.assertEqual(250, widget.pad_button('up').hold_delay())

        # and the settings can change under the widget, the buttons included
        widget.apply_settings(PtzControlSettings(angle_step_deg=45.0, hold_delay_ms=100, zoom_rate_per_s=3.0))
        step, hold = widget.commands()['up']
        self.assertAlmostEqual(-math.radians(45.0), step.pitch)
        self.assertEqual(100, widget.pad_button('up').hold_delay())
        self.assertAlmostEqual(3.0, widget.commands()['zoom_in'][1].zoom)

    def test_the_widget_shows_the_settings_rqt_kept_for_it(self):
        widget = self.make_widget()
        proxy = SettingsProxy()
        widget.apply_settings(PtzControlSettings(velocity_topic='/ptz_tests/kept', angle_step_deg=42.0,
                                                 zoom_topic='/ptz_tests/kept_zoom'))
        widget.save_settings(None, proxy)
        self.assertEqual('/ptz_tests/kept', proxy.values['velocity_topic'])
        self.assertEqual(42.0, float(proxy.values['angle_step_deg']))

        other = PtzControlWidget(self.node)
        self.widgets.append(other)
        other.restore_settings(None, SettingsProxy({name: str(value) for name, value in proxy.values.items()}))
        self.assertEqual('/ptz_tests/kept', other.settings().velocity_topic)
        self.assertAlmostEqual(42.0, other.settings().angle_step_deg)
        self.assertAlmostEqual(math.radians(42.0), abs(other.commands()['up'][0].pitch))
        # what nobody stored is left as the widget has it, and the widget says what it shows
        other.restore_settings(None, SettingsProxy({'velocity_topic': '/ptz_tests/other'}))
        self.assertAlmostEqual(42.0, other.settings().angle_step_deg)
        self.assertEqual('/ptz_tests/other', other.settings().velocity_topic)

    def test_the_settings_of_the_widget_can_be_given_on_the_command_line(self):
        defaults = PtzControlSettings(angle_step_deg=15.0)
        settings, given = PtzControlSettings.from_args([
            '--velocity-topic', '/ptz/cli/velocity',
            '--angle-step-deg', '30',
            '--command-rate-hz', '25',
            '--somebody-elses-argument', 'whatever',
        ], defaults=defaults)
        self.assertEqual('/ptz/cli/velocity', settings.velocity_topic)
        self.assertAlmostEqual(30.0, settings.angle_step_deg)
        self.assertAlmostEqual(25.0, settings.command_rate_hz)
        self.assertEqual(defaults.zoom_topic, settings.zoom_topic)
        self.assertEqual({'velocity_topic', 'angle_step_deg', 'command_rate_hz'}, given)
        untouched, nothing = PtzControlSettings.from_args([], defaults=defaults)
        self.assertEqual(defaults, untouched)
        self.assertEqual(set(), nothing)


class PluginTest(RosGuiTest):
    """What the plugin does around the widget."""

    def make_context(self, argv=None, serial_number: int = 1):
        """The part of the rqt context a plugin uses, with the node of the test behind it."""
        test_node = self.node

        class Context(QObject):
            """A plugin context, which rqt also uses as the parent of the plugin it builds."""

            def __init__(self):
                super().__init__()
                # rqt gives the node as an attribute and the rest as methods, and the plugin uses
                # exactly that
                self.node = test_node
                self.widgets = []
                self._argv = list(argv or [])
                self._serial = serial_number

            def argv(self):
                return self._argv

            def serial_number(self):
                return self._serial

            def add_widget(self, widget):
                self.widgets.append(widget)

        return Context()

    def test_the_plugin_shows_its_widget_in_the_window(self):
        context = self.make_context()
        plugin = PtzControl(context)
        self.addCleanup(plugin.shutdown_plugin)
        self.assertEqual('PtzControl', plugin.objectName())
        self.assertEqual([plugin.widget()], context.widgets)  # rqt was told to show the widget
        self.assertEqual('PTZ Control', plugin.widget().windowTitle())
        self.assertEqual(PtzControlSettings(), plugin.widget().settings())

    def test_the_plugin_shows_what_the_command_line_asked_for(self):
        plugin = PtzControl(self.make_context(argv=['--angle-step-deg', '45', '--velocity-topic', '/ptz/cli/vel']))
        self.addCleanup(plugin.shutdown_plugin)
        self.assertAlmostEqual(45.0, plugin.widget().settings().angle_step_deg)
        self.assertEqual('/ptz/cli/vel', plugin.widget().settings().velocity_topic)
        # what the command line says wins over what rqt kept, but only the first time
        proxy = SettingsProxy({'angle_step_deg': 10.0})
        plugin.restore_settings(None, proxy)
        self.assertAlmostEqual(45.0, plugin.widget().settings().angle_step_deg)
        plugin.restore_settings(None, SettingsProxy({'angle_step_deg': 10.0}))
        self.assertAlmostEqual(10.0, plugin.widget().settings().angle_step_deg)

    def test_a_second_plugin_of_the_same_kind_says_so_in_its_title(self):
        # rqt lets the operator open the plugin more than once, and the windows have to tell apart
        plugin = PtzControl(self.make_context(serial_number=2))
        self.addCleanup(plugin.shutdown_plugin)
        self.assertEqual('PTZ Control (2)', plugin.widget().windowTitle())


class DialogTest(GuiTest):
    """The dialog asking for the settings of the PTZ control plugin."""

    def test_the_dialog_asks_for_the_topics_and_for_the_amplitudes(self):
        dialog = SettingsDialog[PtzControlSettings](PtzControlSettings(velocity_topic='/ptz/dialog/velocity'))
        self.addCleanup(dialog.deleteLater)
        self.assertEqual({item.name for item in fields(PtzControlSettings)}, dialog.settings_names())
        self.assertEqual('/ptz/dialog/velocity', dialog.widget('velocity_topic').text())
        dialog.widget('velocity_topic').setText('/ptz/dialog/other')
        dialog.widget('angle_step_deg').setValue(33.0)
        changed = dialog.settings()
        self.assertEqual('/ptz/dialog/other', changed.velocity_topic)
        self.assertAlmostEqual(33.0, changed.angle_step_deg)
        self.assertAlmostEqual(20.0, changed.angle_rate_deg_per_s)
