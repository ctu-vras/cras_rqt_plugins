# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Tests of the buttons calling ROS services."""

import os
import re
import threading
import time
import unittest
from dataclasses import fields
from unittest.mock import patch

# The tests build real widgets but we don't want to show them when running on a machine with a display.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import launch  # noqa: F401
import launch_ros  # noqa: F401
import rclpy  # noqa: E402
from cras_rqt_buttons.button_settings import ClickButtonSettings, HoldButtonSettings  # noqa: E402
from cras_rqt_buttons.click_button_widget import TriggerButtonWidget  # noqa: E402
from cras_rqt_buttons.hold_button_widget import SetBoolButtonWidget  # noqa: E402
from cras_rqt_buttons.set_bool_button import CrasRqtSetBoolButton  # noqa: E402
from cras_rqt_buttons.trigger_button import CrasRqtTriggerButton  # noqa: E402
from cras_rqt_common.color import Color  # noqa: E402
from cras_rqt_common.settings_dialog import SettingsDialog  # noqa: E402
from python_qt_binding.QtCore import QEvent, QObject, Qt  # noqa: E402
from python_qt_binding.QtGui import QMouseEvent, QPalette  # noqa: E402
from python_qt_binding.QtWidgets import QApplication, QDialog  # noqa: E402
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from std_srvs.srv import SetBool, Trigger  # noqa: E402

try:
    # Qt6
    from python_qt_binding.QtCore import QPointF
except AttributeError:
    # Qt5
    from python_qt_binding.QtCore import QPoint
    QPointF = QPoint


class SettingsProxy:
    """A stand-in for the settings proxy rqt hands to the plugins."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, name, default=None):
        return self.values.get(name, default)

    def set_value(self, name, value):
        self.values[name] = value


class ClosingConfigurationDialog(SettingsDialog):
    """
    The configuration dialog that remembers itself and closes right away.

    A configuration opened from a widget or a plugin would wait for a user pressing a button, and
    that is nobody's part in a test.
    """

    opened: list = []

    def __init__(self, *args, **kwargs):
        # the arguments are passed on as they came, so a widget that hands them over the wrong way
        # still fails here the way it fails in front of the user
        super().__init__(*args, **kwargs)
        ClosingConfigurationDialog.opened.append(self)

    def exec(self, *args):
        return QDialog.DialogCode.Rejected


class RosGuiTest(unittest.TestCase):
    """
    A ROS node and a GUI driven from one single thread.

    :meth:`spin` interleaves spinning the ROS node and processing the GUI events, so nothing runs
    in parallel and every test sees the requests and the responses in the order it triggers them.
    """

    @classmethod
    def setUpClass(cls):
        if not rclpy.ok():
            rclpy.init()
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = Node('button_tests')
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.extra_nodes = []
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.shutdown()
            widget.deleteLater()
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

    def serve(self, service_type, name, handler, node: Node = None):
        """Offer a service; by default from the node the buttons talk to, so it is answered."""
        node = node if node is not None else self.node
        if node not in self.extra_nodes and node is not self.node:
            self.extra_nodes.append(node)
        return node.create_service(service_type, name, handler)

    def silent_service(self, service_type, name, node_name):
        """
        Offer a service that does not answer until the test says so.

        The node offering the service is not spun by anybody, so a request sent to it stays on its
        way, which is how a button can be watched while it is still waiting for an answer.

        :returns: the node offering the service, to be handed to :meth:`wake_up`
        """
        node = Node(node_name)
        self.serve(service_type, name, self.accepted, node=node)
        return node

    def wake_up(self, node) -> None:
        """Let a node made by :meth:`silent_service` answer the requests it has been given."""
        self.executor.add_node(node)
        self.addCleanup(self.executor.remove_node, node)

    def make_widget(self, widget_type, service_type, service_name, handler, **settings):
        """
        Create a button and a service of the matching type next to it.

        :param handler: called with every request, returns the response to send back
        :returns: the widget and the list the requests are recorded into
        """
        requests = []

        def record(request, response):
            requests.append(request)
            return handler(request, response)

        self.service = self.serve(service_type, service_name, record)
        widget = widget_type(self.node)
        self.widgets.append(widget)
        _settings = dict(service_name=service_name)
        _settings.update(settings)
        widget.apply_settings(widget_type.SETTINGS_TYPE.load(SettingsProxy(_settings)))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()),
                        f'the button never noticed service {service_name}')
        return widget, requests

    @staticmethod
    def accepted(request, response):
        """A service handler that is always happy about the request."""
        response.success = True
        response.message = 'ok'
        return response

    def press(self, widget, wait: float = 0.3) -> None:
        """
        Press the button the way a finger or a mouse would.

        A touch on a button is turned into these mouse events by Qt itself, so sending them to the
        button covers both ways of operating it.

        :param wait: how long to let the request travel to the service and back; ``None`` leaves it
            on the way, which is how to see what the button does before a response arrives
        """
        self._mouse_event(widget, QEvent.Type.MouseButtonPress, wait)

    def release(self, widget, wait: float = 0.3) -> None:
        """Let the button go."""
        self._mouse_event(widget, QEvent.Type.MouseButtonRelease, wait)

    def click(self, widget, wait: float = 0.3) -> None:
        """Press and release the button in one go."""
        self.press(widget, wait=wait)
        self.release(widget, wait=wait)

    def _mouse_event(self, widget, event_type, wait) -> None:
        button = widget.button
        pressed = Qt.MouseButton.LeftButton if event_type == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
        event = QMouseEvent(event_type, QPointF(button.rect().center()), Qt.MouseButton.LeftButton, pressed,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(button, event)
        self.app.processEvents()
        if wait is not None:
            self.spin(wait)


class ButtonTest(RosGuiTest):
    """How the buttons behave towards the operator and towards the service."""

    @staticmethod
    def painted_background(widget):
        """The color the button is painted with, and nothing if the Qt style paints it itself."""
        ordinary = widget.button.styleSheet().split(':pressed')[0]
        painted = re.search(r'background-color: (#[0-9a-fA-F]{6})', ordinary)
        return Color(painted.group(1)) if painted else None

    @staticmethod
    def standard_background(widget) -> Color:
        """The color an ordinary button of the Qt style in use is painted with."""
        # not the palette of the button itself, which already knows about the style sheet it is
        # painted with while it is waiting for an answer
        return Color(widget.palette().color(QPalette.ColorRole.Button))

    def test_disabled_while_there_is_no_service(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/missing'))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())
        self.assertIn('Waiting for service', widget.button.toolTip())
        self.assertEqual('', widget.button.styleSheet())  # a Qt button shows it is disabled too

    def test_enabled_once_the_service_shows_up_and_disabled_again_once_it_gone(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/appearing'))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())

        service = self.serve(Trigger, '/button_tests/appearing', self.accepted)
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))

        self.node.destroy_service(service)
        self.assertTrue(self.spin_until(lambda: not widget.button.isEnabled()))

    def test_no_service_configured_at_all(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name=''))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())
        self.click(widget)  # an unconfigured button must not raise either
        self.assertFalse(widget.is_error())

    def test_pressing_a_disabled_button_calls_nothing(self):
        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/vanishing', self.accepted)
        self.node.destroy_service(self.service)  # the mission server dies
        self.assertTrue(self.spin_until(lambda: not widget.button.isEnabled()))
        self.click(widget)
        self.assertEqual([], requests)
        self.assertFalse(widget.is_error())

    # the trigger button

    def test_trigger_button_calls_the_service(self):
        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/patrol', self.accepted, button_text='Patrol')
        self.assertEqual('Patrol', widget.button.text())
        self.click(widget)
        self.assertEqual(1, len(requests))
        self.assertEqual(0, widget.pending_requests())
        self.assertIn('/button_tests/patrol', widget.button.toolTip())

    def test_trigger_button_stays_plain_when_the_service_is_happy(self):
        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/home', self.accepted)
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertEqual(1, len(requests))
        self.assertFalse(widget.is_error())
        self.assertEqual('', widget.button.styleSheet())

    def test_trigger_button_turns_red_when_the_service_refuses(self):
        answered = []

        def refuses_the_first_time(request, response):
            response.success = bool(answered)  # only the very first request is refused
            response.message = 'ok' if answered else 'not while the battery is warm'
            answered.append(request)
            return response

        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/stop', refuses_the_first_time,
            button_text='Stop', button_color='#4a90d9', error_color='#ff0000')
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error()))
        self.assertIn('#ff0000', widget.button.styleSheet())
        self.assertIn('not while the battery is warm', widget.button.toolTip())

        self.press(widget, wait=None)
        self.assertFalse(widget.is_error())  # the red goes away as soon as the user acts again
        self.release(widget)
        self.assertEqual(2, len(requests))
        self.assertFalse(widget.is_error())
        self.assertIn('#4a90d9', widget.button.styleSheet())

    def test_trigger_button_turns_red_when_the_service_never_answers(self):
        silent_node = Node('button_tests_silent_server')
        self.serve(Trigger, '/button_tests/silent', self.accepted, node=silent_node)
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(
            service_name='/button_tests/silent', response_timeout=0.2))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error(), timeout=3.0))
        self.assertIn('did not respond', widget.button.toolTip())

    # a button that has something to wait for

    def test_the_button_goes_dark_while_the_service_thinks(self):
        server = self.silent_service(Trigger, '/button_tests/thinking', 'button_tests_thinking')
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/thinking',
                                                    button_color=Color('#4a90d9')))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))
        self.assertEqual(Color('#4a90d9'), self.painted_background(widget))

        self.click(widget, wait=None)  # the request is on its way and nothing answered yet
        self.assertTrue(widget.is_waiting())
        self.assertFalse(widget.is_active())  # a button that is only clicked is never active
        self.assertLess(self.painted_background(widget).lightness(),
                        Color('#4a90d9').lightness(), 'the button does not look busy at all')
        self.assertIn('Waiting for /button_tests/thinking to answer', widget.button.toolTip())

        self.wake_up(server)  # the service gets to answer at last
        self.assertTrue(self.spin_until(lambda: not widget.is_waiting()))
        self.assertEqual(Color('#4a90d9'), self.painted_background(widget))
        self.assertNotIn('to answer', widget.button.toolTip())

    def test_a_button_without_a_color_of_its_own_goes_dark_too(self):
        server = self.silent_service(Trigger, '/button_tests/thinking_plain', 'button_tests_thinking_plain')
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/thinking_plain'))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))
        self.assertEqual('', widget.button.styleSheet())  # the look of an ordinary Qt button

        self.click(widget, wait=None)
        self.assertTrue(widget.is_waiting())
        # it has no color of its own, so it is darkened from the color the Qt style paints with
        self.assertLess(self.painted_background(widget).lightness(),
                        self.standard_background(widget).lightness())

        self.wake_up(server)
        self.assertTrue(self.spin_until(lambda: not widget.is_waiting()))
        self.assertEqual('', widget.button.styleSheet())

    def test_a_button_that_gives_up_on_a_call_stops_looking_busy(self):
        self.silent_service(Trigger, '/button_tests/dull', 'button_tests_dull')
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/dull', response_timeout=0.2))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))
        self.click(widget, wait=None)
        self.assertTrue(widget.is_waiting())
        self.assertTrue(self.spin_until(lambda: widget.is_error(), timeout=3.0))
        self.assertFalse(widget.is_waiting())  # it is not waiting anymore, so it says so either
        # it is not waiting, so it complains about the call instead
        self.assertEqual(Color('#c62828'), self.painted_background(widget))

    # sending a request that did not work once again

    def test_by_default_the_service_is_asked_only_once(self):
        def refuses(request, response):
            response.success = False
            response.message = 'the mission is busy'
            return response

        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/busy_once', refuses)
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error()))
        self.assertEqual(1, len(requests))

    def test_a_request_that_is_refused_is_sent_again_until_it_works(self):
        answered = []

        def refuses_the_first_two(request, response):
            response.success = len(answered) > 1
            response.message = 'ok' if response.success else 'the mission is starting'
            answered.append(request)
            return response

        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/flaky', refuses_the_first_two,
            button_color='#4a90d9', call_attempts=3)
        self.click(widget, wait=None)
        self.assertTrue(widget.is_waiting())
        self.spin(0.2)  # an attempt that did not work is being sent again right now
        self.assertTrue(widget.is_waiting())
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0, timeout=5.0))
        self.assertEqual(3, len(requests))
        # in the end the service took the request, so the button has nothing to complain about
        self.assertFalse(widget.is_error())
        self.assertFalse(widget.is_waiting())
        self.assertEqual(Color('#4a90d9'), self.painted_background(widget))

    def test_a_request_that_never_works_is_given_up_on(self):
        def refuses(request, response):
            response.success = False
            response.message = 'the mission is busy'
            return response

        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/always_busy', refuses,
            call_attempts=4, error_color='#ff0000')
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error(), timeout=5.0))
        self.assertEqual(4, len(requests))  # the attempts are used up, and the button complains
        self.assertIn('the mission is busy', widget.button.toolTip())
        self.assertIn('#ff0000', widget.button.styleSheet())
        self.assertFalse(widget.is_waiting())

    # a button that is held

    def test_a_button_that_is_held_calls_with_true_when_pushed_and_false_when_released(self):
        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/speak', self.accepted,
            button_text='Speak')
        self.press(widget)
        self.assertEqual([True], [request.data for request in requests])
        self.release(widget)
        self.assertEqual([True, False], [request.data for request in requests])
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertFalse(widget.is_error())

    def test_the_red_is_about_the_call_that_matters(self):
        def refuses_press(request, response):
            response.success = not request.data  # only holding the button is refused
            response.message = 'the loudspeaker is busy'
            return response

        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/speak_busy', refuses_press)
        self.press(widget, wait=None)    # the response to the press is still on its way when
        self.release(widget, wait=None)  # the release happens, so the press is not the news
        self.spin(0.5)
        self.assertEqual([True, False], [request.data for request in requests])
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertFalse(widget.is_error())

    def test_a_button_that_is_held_turns_red_when_the_release_fails(self):
        def refuses_release(request, response):
            response.success = request.data  # holding is fine, letting go is refused
            response.message = 'the loudspeaker is busy'
            return response

        widget, _ = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/speak_busy2', refuses_release)
        self.press(widget)
        self.release(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error()))
        self.assertIn('#c62828', widget.button.styleSheet())
        self.assertIn('the loudspeaker is busy', widget.button.toolTip())

    def test_releasing_a_hidden_button_still_calls_with_false(self):
        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/speak_hidden', self.accepted)
        widget.show()
        self.app.processEvents()
        self.press(widget, wait=None)
        widget.hide()  # e.g. the dock with the button was closed under the finger
        self.spin(0.3)
        self.assertEqual([True, False], [request.data for request in requests])

    def test_a_button_that_is_held_can_send_the_opposite_value(self):
        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/speak_inverted', self.accepted, invert_value=True)
        self.press(widget)
        self.assertEqual([False], [request.data for request in requests])
        self.assertIn('with false while held and with true when released', widget.button.toolTip())
        self.release(widget)
        self.assertEqual([False, True], [request.data for request in requests])
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertFalse(widget.is_error())

    def test_releasing_a_hidden_inverted_button_still_calls_with_true(self):
        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/speak_hidden_inverted', self.accepted, invert_value=True)
        widget.show()
        self.app.processEvents()
        self.press(widget, wait=None)
        widget.hide()  # the button let go of by closing its dock sends the value of a release too
        self.spin(0.3)
        self.assertEqual([False, True], [request.data for request in requests])

    def test_a_button_that_is_only_clicked_has_no_value_to_invert(self):
        # a button that sends no value has nothing to invert, so it does not even ask for it
        self.assertNotIn('invert_value', {item.name for item in fields(ClickButtonSettings)})
        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/patrol', self.accepted)
        self.click(widget)
        self.assertEqual(1, len(requests))
        self.assertFalse(widget.is_error())

    # what a button that is held shows while it is held

    def test_a_button_that_is_held_shows_that_it_registered_the_press(self):
        self.silent_service(SetBool, '/button_tests/ptt', 'button_tests_ptt_press')
        widget = SetBoolButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(HoldButtonSettings(service_name='/button_tests/ptt'))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))

        self.press(widget, wait=None)  # the service never gets to answer the press
        self.assertTrue(widget.is_waiting())
        self.assertFalse(widget.is_active())  # holding is not accepted until the service says so
        self.assertLess(self.painted_background(widget).lightness(), self.standard_background(widget).lightness())
        self.assertIn('Registered the press, waiting for /button_tests/ptt to accept it', widget.button.toolTip())

    def test_a_button_that_is_held_shows_that_it_registered_the_release(self):
        server = self.silent_service(SetBool, '/button_tests/ptt_release', 'button_tests_ptt_rel')
        widget = SetBoolButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(HoldButtonSettings(service_name='/button_tests/ptt_release'))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))

        self.press(widget, wait=None)
        self.release(widget, wait=None)  # let go of the button while the press is still on its way
        self.assertTrue(widget.is_waiting())
        self.assertIn('Registered the release', widget.button.toolTip())
        self.assertNotIn('Registered the press', widget.button.toolTip())

        self.wake_up(server)  # both requests are answered at last
        self.assertTrue(self.spin_until(lambda: not widget.is_waiting()))
        self.assertFalse(widget.is_active())  # the service was told that the button is free again
        self.assertEqual('', widget.button.styleSheet())

    def test_a_button_that_is_held_is_active_once_the_service_takes_the_press(self):
        widget, _ = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/ptt_ready', self.accepted,
            button_color='#f9a825', active_color='#00aa00', active_text_color='black')
        self.press(widget)
        self.assertTrue(widget.is_active())
        self.assertFalse(widget.is_waiting())
        sheet = widget.button.styleSheet()
        self.assertEqual(Color('#00aa00'), self.painted_background(widget))
        self.assertNotIn('#f9a825', sheet)  # while it is held, the active color is what is painted
        self.assertIn('color: #000000;', sheet)  # the text color asked for, not the ordinary one

        self.release(widget)
        self.assertTrue(self.spin_until(lambda: not widget.is_active()))
        self.assertEqual(Color('#f9a825'), self.painted_background(widget))

    def test_a_button_that_is_held_is_active_for_the_value_it_sends_while_held(self):
        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/ptt_inverted_active', self.accepted,
            invert_value=True, active_color='#00aa00')
        self.press(widget)
        self.assertEqual([False], [request.data for request in requests])
        # an inverted button holds false, so that is the value the button is active for
        self.assertTrue(widget.is_active())
        self.assertEqual(Color('#00aa00'), self.painted_background(widget))
        self.release(widget)
        self.assertTrue(self.spin_until(lambda: not widget.is_active()))

    def test_a_press_that_the_service_refuses_does_not_make_the_button_active(self):
        def refuses_press(request, response):
            response.success = not request.data
            response.message = 'the loudspeaker is busy'
            return response

        widget, _ = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/ptt_refused', refuses_press, active_color='#00aa00')
        self.press(widget)
        self.assertFalse(widget.is_active())
        self.assertNotIn('#00aa00', widget.button.styleSheet())
        self.assertIn('#c62828', widget.button.styleSheet())  # the failure is what is shown now

    def test_the_button_stays_active_until_the_release_goes_through(self):
        releases = []

        def refuses_the_first_release(request, response):
            if not request.data:
                releases.append(request)
            response.success = request.data or len(releases) > 1
            response.message = 'the loudspeaker is still busy'
            return response

        widget, requests = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/ptt_hard_release', refuses_the_first_release,
            active_color='#00aa00', call_attempts=3)
        self.press(widget)
        self.assertTrue(widget.is_active())

        self.release(widget, wait=None)
        self.assertTrue(widget.is_waiting())  # the release was registered and is on its way
        self.assertTrue(widget.is_active())  # and until it goes through, the button is still held
        self.assertIn('Registered the release', widget.button.toolTip())
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0, timeout=5.0))
        self.assertEqual([True, False, False], [request.data for request in requests])
        self.assertFalse(widget.is_error())
        self.assertFalse(widget.is_active())

    def test_a_button_without_active_colors_keeps_the_color_it_has_anyway(self):
        widget, _ = self.make_widget(
            SetBoolButtonWidget, SetBool, '/button_tests/ptt_no_active', self.accepted, button_color='#f9a825')
        self.assertIsNone(widget.settings().active_color)
        self.press(widget)
        self.assertTrue(widget.is_active())
        self.assertEqual(Color('#f9a825'), self.painted_background(widget))
        self.release(widget)
        self.assertTrue(self.spin_until(lambda: not widget.is_active()))
        self.assertEqual(Color('#f9a825'), self.painted_background(widget))

    # the way the button looks

    def test_it_looks_like_a_standard_qt_button_by_default(self):
        for widget_type in (TriggerButtonWidget, SetBoolButtonWidget):
            widget = widget_type(self.node)
            self.widgets.append(widget)
            self.assertEqual('', widget.button.styleSheet())
            self.assertIsNone(widget.settings().button_color)
            self.assertIsNone(widget.settings().text_color)
            widget.apply_settings(widget_type.SETTINGS_TYPE(
                service_name=f'/button_tests/missing_{widget_type.__name__}'))
            self.spin(0.3)
            self.assertFalse(widget.button.isEnabled())
            self.assertEqual('', widget.button.styleSheet(), f'{widget_type.__name__} paints over the standard look')

    def test_only_the_colors_that_were_asked_for_are_painted(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/missing', text_color=Color('#00ff00')))
        self.assertIn('color: #00ff00;', widget.button.styleSheet())
        self.assertNotIn('background-color', widget.button.styleSheet())

        widget.apply_settings(ClickButtonSettings(service_name='/button_tests/missing', button_color=Color('black')))
        self.assertIn('background-color: #000000;', widget.button.styleSheet())
        self.assertIn('color: #ffffff;', widget.button.styleSheet())  # so the text stays readable

    def test_the_color_of_a_button_is_painted_for_that_one_button(self):
        # a style sheet reaches everything inside the widget it is set on, so a rule that is not
        # tied to the button itself would also paint the widgets around it
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(
            service_name='/button_tests/missing', button_color=Color('#4a90d9'), text_color=Color('white'),
            error_color=Color('#c62828')))
        name = f'#{widget.button.objectName()}'
        sheet = widget.button.styleSheet()
        self.assertNotEqual('', sheet)
        for rule in sheet.split('}')[:-1]:
            self.assertIn(name, rule.split('{')[0], f'{rule} is not tied to the button itself')

    def test_a_painted_button_fades_out_when_it_cannot_be_used(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(
            ClickButtonSettings(service_name='/button_tests/missing', button_color=Color('#4a90d9')))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())
        self.assertIn('rgba(74, 144, 217, 90)', widget.button.styleSheet())

    def test_a_failure_is_readable_even_with_a_dark_text_color(self):
        def refuses(request, response):
            response.success = False
            response.message = 'the mission is busy'
            return response

        widget, _ = self.make_widget(TriggerButtonWidget, Trigger, '/button_tests/busy', refuses, text_color='black')
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error()))
        self.assertIn('background-color: #c62828;', widget.button.styleSheet())
        self.assertIn('color: #ffffff;', widget.button.styleSheet())

    def test_it_is_big_enough_for_a_finger(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        self.assertGreaterEqual(widget.minimumWidth(), 100)
        self.assertGreaterEqual(widget.minimumHeight(), 100)
        self.assertGreaterEqual(widget.button.minimumWidth(), 100)
        self.assertGreaterEqual(widget.button.minimumHeight(), 100)

    def test_text_grows_with_the_button(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ClickButtonSettings(button_text='Patrol'))
        widget.show()
        self.app.processEvents()
        widget.resize(200, 200)
        self.app.processEvents()
        small = widget.button.font().pointSizeF()
        widget.resize(700, 700)
        self.app.processEvents()
        large = widget.button.font().pointSizeF()
        widget.resize(150, 150)
        self.app.processEvents()
        smallest = widget.button.font().pointSizeF()
        self.assertGreater(large, small)
        self.assertGreater(small, smallest)
        self.assertLessEqual(smallest, widget.FONT_MAX_POINTS)

    def test_settings_are_stored_and_reloaded(self):
        widget = SetBoolButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(HoldButtonSettings(
            service_name='/button_tests/stored', button_text='Home', button_color=Color('yellow'),
            text_color=Color('black'), error_color=Color('blue'), active_color=Color('green'),
            active_text_color=Color('white'), response_timeout=3.0, call_attempts=4, invert_value=True))
        proxy = SettingsProxy()
        widget.save_settings(None, proxy)
        self.assertEqual('/button_tests/stored', proxy.values['service_name'])
        # rqt keeps everything as text, so the settings come back as text too
        proxy = SettingsProxy({name: str(value) for name, value in proxy.values.items()})

        other = SetBoolButtonWidget(self.node)
        self.widgets.append(other)
        other.restore_settings(None, proxy)
        self.assertEqual(HoldButtonSettings(
            service_name='/button_tests/stored', button_text='Home', button_color=Color('#ffffff00'),
            text_color=Color('#ff000000'), error_color=Color('#ff0000ff'), active_color=Color('#ff008000'),
            active_text_color=Color('#ffffffff'), response_timeout=3.0, call_attempts=4, invert_value=True,
        ), other.settings())
        self.assertIsInstance(other.settings().call_attempts, int)  # a count, not a decimal number
        self.assertEqual('Home', other.button.text())
        self.assertIn('#ffff00', other.button.styleSheet())

    def test_an_empty_color_asks_for_the_color_of_a_standard_qt_button(self):
        settings = HoldButtonSettings.load(SettingsProxy({
            'button_color': '', 'text_color': '   ', 'invert_value': 'maybe'}))
        self.assertIsNone(settings.button_color)
        self.assertIsNone(settings.text_color)
        self.assertFalse(settings.invert_value)  # nobody can tell what 'maybe' means
        # a failed call has to stay visible, so a color that cannot be taken away has one anyway
        self.assertEqual(HoldButtonSettings().error_color, settings.error_color)

    def test_a_color_that_makes_no_sense_is_left_out(self):
        stored = SettingsProxy({'button_color': 'yellow'})
        settings = ClickButtonSettings.load(stored)
        self.assertEqual(Color('yellow'), settings.button_color)
        broken = SettingsProxy({'button_color': 'not a color at all'})
        # a color that can be taken away has no way of telling junk from a color taken away on
        # purpose, so what is left is a button painted the way an ordinary Qt button is
        self.assertIsNone(ClickButtonSettings.load(broken).button_color)

    def test_the_configuration_dialog_asks_for_what_the_button_can_use(self):
        # what a button can do is decided by its settings, so the dialog of a button that is held has
        # something to ask for that the dialog of a button that is only clicked never mentions
        for_hold = SettingsDialog(HoldButtonSettings())
        self.addCleanup(for_hold.deleteLater)
        for_click = SettingsDialog(ClickButtonSettings())
        self.addCleanup(for_click.deleteLater)
        self.assertTrue(for_hold.widget('invert_value').isEnabled())
        self.assertIn('active_color', for_hold.settings_names())
        for name in ('invert_value', 'active_color', 'active_text_color'):
            self.assertNotIn(name, for_click.settings_names())
        # a button that is only clicked waits for one call just as much as a button that is held
        self.assertIn('call_attempts', for_click.settings_names())

    def test_the_configuration_dialog_opens_the_way_the_button_asks_for_it(self):
        # opening the configuration used to end with a TypeError about the arguments of the dialog,
        # so the user could not configure a button at all
        for widget_class, held in ((TriggerButtonWidget, False), (SetBoolButtonWidget, True)):
            with self.subTest(button=widget_class.__name__):
                widget = widget_class(self.node)
                self.widgets.append(widget)
                ClosingConfigurationDialog.opened = []
                with patch.object(widget_class, 'DIALOG_TYPE', ClosingConfigurationDialog):
                    widget.open_configuration()
                self.assertEqual(1, len(ClosingConfigurationDialog.opened), 'the configuration did not open')
                dialog = ClosingConfigurationDialog.opened[0]
                self.addCleanup(dialog.deleteLater)
                self.assertEqual(f'{widget._window_title} configuration', dialog.windowTitle())
                # what the button can do decides what the dialog asks for, and the setting the
                # dialog does not ask for is kept rather than replaced by a default
                self.assertEqual(held, 'invert_value' in dialog.settings_names())
                self.assertEqual(widget.settings(), dialog.settings())

    def test_broken_settings_are_ignored(self):
        proxy = SettingsProxy({
            'service_name': '   ',
            'button_text': None,
            'button_color': 'not a color at all',
            'text_color': '#00ff00',
            'error_color': 12345,
            'active_color': 'not a color either',
            'response_timeout': 'yesterday',
            'call_attempts': 'a lot',
        })
        settings = HoldButtonSettings.load(proxy)
        defaults = HoldButtonSettings()
        self.assertEqual(defaults.service_name, settings.service_name)
        self.assertEqual(defaults.button_text, settings.button_text)
        self.assertIsNone(settings.button_color)
        self.assertEqual(Color('#00ff00'), settings.text_color)
        self.assertEqual(defaults.error_color, settings.error_color)
        self.assertEqual(defaults.active_color, settings.active_color)
        self.assertEqual(defaults.response_timeout, settings.response_timeout)
        self.assertEqual(defaults.call_attempts, settings.call_attempts)
        # a number that is out of what the button can be asked for is kept within the range
        self.assertEqual(10, HoldButtonSettings.load(SettingsProxy({'call_attempts': '400'})).call_attempts)
        self.assertEqual(1, HoldButtonSettings.load(SettingsProxy({'call_attempts': '-4'})).call_attempts)

    def test_settings_can_be_given_as_arguments(self):
        defaults = HoldButtonSettings(button_text='Trigger')
        settings, given = HoldButtonSettings.from_args([
            '--service-name', '/mission/patrol',
            '--button_text', 'Patrol',
            '--button-color', 'red',
            '--response-timeout', '2.5',
            '--call-attempts', '4',
            '--invert-value',  # a switch does not need a value of its own
            '--somebody-elses-argument', 'whatever',
        ], defaults=defaults)
        self.assertEqual('/mission/patrol', settings.service_name)
        self.assertEqual('Patrol', settings.button_text)
        self.assertEqual(Color('red'), settings.button_color)
        self.assertEqual(2.5, settings.response_timeout)
        self.assertEqual(4, settings.call_attempts)
        self.assertEqual(defaults.text_color, settings.text_color)
        self.assertTrue(settings.invert_value)
        self.assertEqual({'service_name', 'button_text', 'button_color', 'response_timeout',
                          'call_attempts', 'invert_value'}, given)

        # a switch is turned on by naming it, and left alone when the command line does not say
        # anything about it; the parser has no way of being told to turn a switch off
        said_yes, given = HoldButtonSettings.from_args(['--invert_value'])
        self.assertTrue(said_yes.invert_value)
        self.assertEqual({'invert_value'}, given)
        # invert_value is a bool flag which means it never uses the default value (the fact that the flag is missing
        # means the setting is False)
        kept, nothing = HoldButtonSettings.from_args([], defaults=HoldButtonSettings(invert_value=True))
        self.assertFalse(kept.invert_value)
        self.assertEqual({'invert_value'}, nothing)

        untouched, nothing_given = HoldButtonSettings.from_args([], defaults=defaults)
        self.assertEqual(defaults, untouched)
        self.assertEqual({'invert_value'}, nothing_given)


class ThreadedTest(unittest.TestCase):
    """What happens when nobody waits for the ROS answers in the thread that shows the button."""

    @classmethod
    def setUpClass(cls):
        if not rclpy.ok():
            rclpy.init()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # rqt spins the node of its plugins in a thread of its own, and the thread that shows the
        # widgets only processes the Qt events, which is what this test drives.
        self.gui_node = Node('button_tests_gui')
        self.server_node = Node('button_tests_server')
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.gui_node)
        self.executor.add_node(self.server_node)
        self.spin_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.spin_thread.start()

    def tearDown(self):
        self.executor.shutdown()
        self.spin_thread.join(timeout=5.0)
        self.server_node.destroy_node()
        self.gui_node.destroy_node()

    def process_for(self, seconds: float) -> None:
        """Let the GUI do its work, and only the GUI."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)

    def test_pressing_waits_for_nothing(self):
        def slowly(request, response):
            time.sleep(0.5)  # a mission server that takes its time, in its own process
            response.success = True
            return response

        calls = []

        def record(request, response):
            calls.append(request)
            return slowly(request, response)

        self.server_node.create_service(SetBool, '/button_tests/slow', record)
        widget = SetBoolButtonWidget(self.gui_node)
        try:
            widget.apply_settings(HoldButtonSettings(service_name='/button_tests/slow'))
            enabled = False
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not enabled:
                self.process_for(0.05)
                enabled = widget.button.isEnabled()
            self.assertTrue(enabled, 'the button did not notice the service')

            pressed_at = time.monotonic()
            button = widget.button
            QApplication.sendEvent(
                button,
                QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(button.rect().center()),
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            took = time.monotonic() - pressed_at
            self.assertLess(took, 0.2, 'pressing the button had to wait for the service')
            self.assertEqual(1, widget.pending_requests())  # the request is on its way

            self.process_for(2.0)
            self.assertEqual([True], [request.data for request in calls])
            self.assertFalse(widget.is_error())
        finally:
            widget.shutdown()

    def click(self, widget) -> None:
        """Press and release the button the way the operator of the GUI would."""
        button = widget.button
        for event_type, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                                    (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            QApplication.sendEvent(
                button, QMouseEvent(event_type, QPointF(button.rect().center()),
                                    Qt.MouseButton.LeftButton, buttons,
                                    Qt.KeyboardModifier.NoModifier))

    def test_a_request_that_did_not_work_is_sent_again_on_its_own(self):
        # the answer arrives in another thread than the one showing the button, and sending the
        # request once more has to happen in the thread of the button without being asked for it
        calls = []

        def refuses_the_first_time(request, response):
            calls.append(request)
            response.success = len(calls) > 1  # the mission server is only starting
            response.message = 'the mission is starting'
            return response

        self.server_node.create_service(Trigger, '/button_tests/flaky_threaded',
                                        refuses_the_first_time)
        widget = TriggerButtonWidget(self.gui_node)
        try:
            widget.apply_settings(ClickButtonSettings(
                service_name='/button_tests/flaky_threaded', call_attempts=3))
            enabled = False
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not enabled:
                self.process_for(0.05)
                enabled = widget.button.isEnabled()
            self.assertTrue(enabled, 'the button did not notice the service')
            self.click(widget)
            self.assertTrue(widget.is_waiting())
            self.process_for(2.0)
            self.assertEqual(2, len(calls))
            self.assertFalse(widget.is_error())
            self.assertFalse(widget.is_waiting())
        finally:
            widget.shutdown()


class PluginContext(QObject):
    """A stand-in for the RQt plugin context the plugins are handed."""

    def __init__(self, node, argv=(), serial_number=1):
        super().__init__()
        self.node = node
        self.widgets = []
        self._argv = list(argv)
        self._serial_number = serial_number

    def argv(self):
        return self._argv

    def serial_number(self):
        return self._serial_number

    def add_widget(self, widget):
        self.widgets.append(widget)


class PluginTest(RosGuiTest):
    """The RQt plugins put the button into the window and know which settings win."""

    def test_the_button_shows_up_in_the_window(self):
        context = PluginContext(self.node, ['--service_name', '/button_tests/patrol', '--button_text', 'Patrol'])
        plugin = CrasRqtTriggerButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        self.assertEqual(1, len(context.widgets))
        widget = context.widgets[0]
        self.assertIsInstance(widget, TriggerButtonWidget)
        self.assertEqual('Patrol', widget.button.text())
        self.assertEqual('/button_tests/patrol', widget.settings().service_name)
        self.assertIn('Trigger Button', widget.windowTitle())

    def test_the_second_instance_says_so_in_its_title(self):
        context = PluginContext(self.node, [], serial_number=2)
        plugin = CrasRqtSetBoolButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        self.assertIn('(2)', context.widgets[0].windowTitle())
        self.assertIsInstance(context.widgets[0], SetBoolButtonWidget)

    def test_what_is_given_on_the_command_line_wins(self):
        context = PluginContext(self.node, ['--button_text', 'Speak'])
        plugin = CrasRqtSetBoolButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        widget = context.widgets[0]
        stored = SettingsProxy({'button_text': 'Stored in the perspective', 'service_name': '/button_tests/home'})
        plugin.restore_settings(None, stored)
        self.assertEqual('Speak', widget.button.text())
        self.assertEqual('/button_tests/home', widget.settings().service_name)

        saved = SettingsProxy()
        plugin.save_settings(None, saved)
        self.assertEqual('Speak', saved.values['button_text'])
        self.assertEqual('/button_tests/home', saved.values['service_name'])

    def test_a_button_can_be_inverted_from_the_command_line(self):
        context = PluginContext(self.node, ['--invert-value', 'true'])
        plugin = CrasRqtSetBoolButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        widget = context.widgets[0]
        # first restore doesn't override the CLI value
        plugin.restore_settings(None, SettingsProxy({'invert_value': 'False'}))
        self.assertTrue(widget.settings().invert_value)
        # second restore does override the CLI value
        plugin.restore_settings(None, SettingsProxy({'invert_value': 'False'}))
        self.assertFalse(widget.settings().invert_value)

        stored = PluginContext(self.node, [])
        from_perspective = CrasRqtSetBoolButton(stored)
        self.addCleanup(from_perspective.shutdown_plugin)
        from_perspective.restore_settings(None, SettingsProxy({'invert_value': 'True'}))
        self.assertFalse(stored.widgets[0].settings().invert_value)
        from_perspective.restore_settings(None, SettingsProxy({'invert_value': 'True'}))
        self.assertTrue(stored.widgets[0].settings().invert_value)


class MissionLaunchTest(unittest.TestCase):
    """The mission control described in the issue really is launchable."""

    @staticmethod
    def load_launch_file():
        import importlib.util  # the launch files are not part of the python package
        launch_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'launch', 'mission_buttons.launch.py')
        spec = importlib.util.spec_from_file_location('mission_buttons', launch_file)
        mission_buttons = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mission_buttons)
        return mission_buttons

    def test_four_buttons_for_the_mission(self):
        mission_buttons = self.load_launch_file()
        services = [button['service'] for button in mission_buttons.BUTTONS]
        self.assertEqual(['patrol', 'home', 'speak', 'stop'], services)
        self.assertEqual(['Patrol', 'Home', 'Speak', 'Stop'],
                         [button['text'] for button in mission_buttons.BUTTONS])
        # only the talking button is held, the other three just trigger their service
        self.assertEqual(
            ['trigger_button', 'trigger_button', 'set_bool_button', 'empty_button'],
            [button['executable'] for button in mission_buttons.BUTTONS])

    def test_the_buttons_are_launchable(self):
        mission_buttons = self.load_launch_file()
        buttons = mission_buttons.generate_launch_description().entities
        self.assertEqual(4, len(buttons))
        for button, wanted in zip(buttons, mission_buttons.BUTTONS):
            self.assertEqual('cras_rqt_buttons', button.node_package)
            self.assertEqual(wanted['executable'], button.node_executable)
            arguments = mission_buttons.button_arguments(wanted)
            self.assertEqual(f'/mission/{wanted["service"]}', arguments[arguments.index('--service_name') + 1])


if __name__ == '__main__':
    unittest.main()
