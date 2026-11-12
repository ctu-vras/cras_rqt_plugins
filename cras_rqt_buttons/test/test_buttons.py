# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Tests of the buttons calling ROS services."""

import os
import threading
import time
import unittest

if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    # The tests build real widgets, and a headless machine has no screen to build them on.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import rclpy  # noqa: E402
from cras_rqt_buttons.button_settings import ButtonSettings, to_optional_color  # noqa: E402
from cras_rqt_buttons.button_settings_dialog import ButtonSettingsDialog, ColorEditor  # noqa: E402
from cras_rqt_buttons.button_widget import PushButtonWidget, TriggerButtonWidget  # noqa: E402
from cras_rqt_buttons.push_button import CrasRqtPushButton  # noqa: E402
from cras_rqt_buttons.trigger_button import CrasRqtTriggerButton  # noqa: E402
from python_qt_binding.QtCore import QEvent, QObject, Qt  # noqa: E402
from python_qt_binding.QtGui import QMouseEvent  # noqa: E402
from python_qt_binding.QtWidgets import QApplication, QWidget  # noqa: E402
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from std_srvs.srv import SetBool, Trigger  # noqa: E402


class SettingsProxy:
    """A stand-in for the settings proxy rqt hands to the plugins."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, name, default=None):
        return self.values.get(name, default)

    def set_value(self, name, value):
        self.values[name] = value


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
        widget.apply_settings(ButtonSettings(service_name=service_name, **settings))
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
        self._mouse_event(widget, QEvent.MouseButtonPress, wait)

    def release(self, widget, wait: float = 0.3) -> None:
        """Let the button go."""
        self._mouse_event(widget, QEvent.MouseButtonRelease, wait)

    def click(self, widget, wait: float = 0.3) -> None:
        """Press and release the button in one go."""
        self.press(widget, wait=wait)
        self.release(widget, wait=wait)

    def _mouse_event(self, widget, event_type, wait) -> None:
        button = widget.button
        pressed = Qt.LeftButton if event_type == QEvent.MouseButtonPress else Qt.NoButton
        event = QMouseEvent(event_type, button.rect().center(), Qt.LeftButton, pressed,
                            Qt.NoModifier)
        QApplication.sendEvent(button, event)
        self.app.processEvents()
        if wait is not None:
            self.spin(wait)


class ButtonTest(RosGuiTest):
    """How the buttons behave towards the operator and towards the service."""

    def test_disabled_while_there_is_no_service(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(service_name='/button_tests/missing'))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())
        self.assertIn('Waiting for service', widget.button.toolTip())
        self.assertEqual('', widget.button.styleSheet())  # a Qt button shows it is disabled too

    def test_enabled_once_the_service_shows_up_and_disabled_again_once_it_gone(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(service_name='/button_tests/appearing'))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())

        service = self.serve(Trigger, '/button_tests/appearing', self.accepted)
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))

        self.node.destroy_service(service)
        self.assertTrue(self.spin_until(lambda: not widget.button.isEnabled()))

    def test_no_service_configured_at_all(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(service_name=''))
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
            TriggerButtonWidget, Trigger, '/button_tests/patrol', self.accepted,
            button_text='Patrol')
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
        self.assertFalse(widget.is_error())  # the red goes away as soon as the operator acts again
        self.release(widget)
        self.assertEqual(2, len(requests))
        self.assertFalse(widget.is_error())
        self.assertIn('#4a90d9', widget.button.styleSheet())

    def test_trigger_button_turns_red_when_the_service_never_answers(self):
        silent_node = Node('button_tests_silent_server')
        self.serve(Trigger, '/button_tests/silent', self.accepted, node=silent_node)
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(
            service_name='/button_tests/silent', response_timeout=0.2))
        self.assertTrue(self.spin_until(lambda: widget.button.isEnabled()))
        self.click(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error(), timeout=3.0))
        self.assertIn('did not respond', widget.button.toolTip())

    # the push button

    def test_push_button_calls_with_true_when_pushed_and_false_when_released(self):
        widget, requests = self.make_widget(
            PushButtonWidget, SetBool, '/button_tests/speak', self.accepted,
            button_text='Speak')
        self.press(widget)
        self.assertEqual([True], [request.data for request in requests])
        self.release(widget)
        self.assertEqual([True, False], [request.data for request in requests])
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertFalse(widget.is_error())

    def test_push_button_red_is_about_the_call_that_matters(self):
        def refuses_press(request, response):
            response.success = not request.data  # only holding the button is refused
            response.message = 'the loudspeaker is busy'
            return response

        widget, requests = self.make_widget(
            PushButtonWidget, SetBool, '/button_tests/speak_busy', refuses_press)
        self.press(widget, wait=None)    # the response to the press is still on its way when
        self.release(widget, wait=None)  # the release happens, so the press is not the news
        self.spin(0.5)
        self.assertEqual([True, False], [request.data for request in requests])
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertFalse(widget.is_error())

    def test_push_button_turns_red_when_the_release_fails(self):
        def refuses_release(request, response):
            response.success = request.data  # holding is fine, letting go is refused
            response.message = 'the loudspeaker is busy'
            return response

        widget, _ = self.make_widget(
            PushButtonWidget, SetBool, '/button_tests/speak_busy2', refuses_release)
        self.press(widget)
        self.release(widget)
        self.assertTrue(self.spin_until(lambda: widget.is_error()))
        self.assertIn('#c62828', widget.button.styleSheet())
        self.assertIn('the loudspeaker is busy', widget.button.toolTip())

    def test_releasing_a_hidden_button_still_calls_with_false(self):
        widget, requests = self.make_widget(
            PushButtonWidget, SetBool, '/button_tests/speak_hidden', self.accepted)
        widget.show()
        self.app.processEvents()
        self.press(widget, wait=None)
        widget.hide()  # e.g. the dock with the button was closed under the finger
        self.spin(0.3)
        self.assertEqual([True, False], [request.data for request in requests])

    def test_push_button_can_send_the_opposite_value(self):
        widget, requests = self.make_widget(
            PushButtonWidget, SetBool, '/button_tests/speak_inverted', self.accepted,
            invert_value=True)
        self.press(widget)
        self.assertEqual([False], [request.data for request in requests])
        self.assertIn('with false while held and with true when released',
                      widget.button.toolTip())
        self.release(widget)
        self.assertEqual([False, True], [request.data for request in requests])
        self.assertTrue(self.spin_until(lambda: widget.pending_requests() == 0))
        self.assertFalse(widget.is_error())

    def test_releasing_a_hidden_inverted_button_still_calls_with_true(self):
        widget, requests = self.make_widget(
            PushButtonWidget, SetBool, '/button_tests/speak_hidden_inverted', self.accepted,
            invert_value=True)
        widget.show()
        self.app.processEvents()
        self.press(widget, wait=None)
        widget.hide()  # the button let go of by closing its dock sends the value of a release too
        self.spin(0.3)
        self.assertEqual([False, True], [request.data for request in requests])

    def test_a_button_that_is_only_clicked_has_no_value_to_invert(self):
        widget, requests = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/patrol_inverted', self.accepted,
            invert_value=True)  # the setting is simply ignored by a button that sends no value
        self.click(widget)
        self.assertEqual(1, len(requests))
        self.assertFalse(widget.is_error())

    # the way the button looks

    def test_it_looks_like_a_standard_qt_button_by_default(self):
        for widget_type in (TriggerButtonWidget, PushButtonWidget):
            widget = widget_type(self.node)
            self.widgets.append(widget)
            self.assertEqual('', widget.button.styleSheet())
            self.assertEqual('', widget.settings().button_color)
            self.assertEqual('', widget.settings().text_color)
            widget.apply_settings(ButtonSettings(
                service_name=f'/button_tests/missing_{widget_type.__name__}'))
            self.spin(0.3)
            self.assertFalse(widget.button.isEnabled())
            self.assertEqual('', widget.button.styleSheet(),
                             f'{widget_type.__name__} paints over the standard look')

    def test_only_the_colors_that_were_asked_for_are_painted(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(service_name='/button_tests/missing',
                                             text_color='#00ff00'))
        self.assertIn('color: #00ff00;', widget.button.styleSheet())
        self.assertNotIn('background-color', widget.button.styleSheet())

        widget.apply_settings(ButtonSettings(service_name='/button_tests/missing',
                                             button_color='black'))
        self.assertIn('background-color: #000000;', widget.button.styleSheet())
        self.assertIn('color: #ffffff;', widget.button.styleSheet())  # so the text stays readable

    def test_the_color_of_a_button_is_painted_for_that_one_button(self):
        # a style sheet reaches everything inside the widget it is set on, so a rule that is not
        # tied to the button itself would also paint the widgets around it
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(service_name='/button_tests/missing',
                                             button_color='#4a90d9', text_color='white',
                                             error_color='#c62828'))
        name = f'#{widget.button.objectName()}'
        sheet = widget.button.styleSheet()
        self.assertNotEqual('', sheet)
        for rule in sheet.split('}')[:-1]:
            self.assertIn(name, rule.split('{')[0], f'{rule} is not tied to the button itself')

    def test_a_painted_button_fades_out_when_it_cannot_be_used(self):
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(service_name='/button_tests/missing',
                                             button_color='#4a90d9'))
        self.spin(0.3)
        self.assertFalse(widget.button.isEnabled())
        self.assertIn('rgba(74, 144, 217, 90)', widget.button.styleSheet())

    def test_a_failure_is_readable_even_with_a_dark_text_color(self):
        def refuses(request, response):
            response.success = False
            response.message = 'the mission is busy'
            return response

        widget, _ = self.make_widget(
            TriggerButtonWidget, Trigger, '/button_tests/busy', refuses, text_color='black')
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
        widget.apply_settings(ButtonSettings(button_text='Patrol'))
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
        widget = TriggerButtonWidget(self.node)
        self.widgets.append(widget)
        widget.apply_settings(ButtonSettings(
            service_name='/button_tests/stored', button_text='Home', button_color='yellow',
            text_color='black', error_color='blue', response_timeout=3.0, invert_value=True))
        proxy = SettingsProxy()
        widget.save_settings(None, proxy)
        self.assertEqual('/button_tests/stored', proxy.values['service_name'])
        # rqt keeps everything as text, so the settings come back as text too
        proxy = SettingsProxy({name: str(value) for name, value in proxy.values.items()})

        other = TriggerButtonWidget(self.node)
        self.widgets.append(other)
        other.restore_settings(None, proxy)
        self.assertEqual(ButtonSettings(
            service_name='/button_tests/stored', button_text='Home', button_color='#ffff00',
            text_color='#000000', error_color='#0000ff', response_timeout=3.0, invert_value=True,
        ), other.settings())
        self.assertEqual('Home', other.button.text())
        self.assertIn('#ffff00', other.button.styleSheet())

    def test_an_empty_color_asks_for_the_color_of_a_standard_qt_button(self):
        settings = ButtonSettings.load(SettingsProxy({
            'button_color': '', 'text_color': '   ', 'invert_value': 'maybe'}))
        self.assertEqual('', settings.button_color)
        self.assertEqual('', settings.text_color)
        self.assertIsNone(to_optional_color(settings.button_color))
        self.assertFalse(settings.invert_value)  # nobody can tell what 'maybe' means
        self.assertNotEqual('', settings.error_color)  # a failed call has to stay visible

    def test_a_color_that_makes_no_sense_is_left_out(self):
        stored = SettingsProxy({'button_color': 'yellow'})
        settings = ButtonSettings.load(stored)
        self.assertEqual('#ffff00', settings.button_color)
        broken = SettingsProxy({'button_color': 'not a color at all'})
        self.assertEqual('', ButtonSettings.load(broken).button_color)
        # and a setting that used to be good does not turn into the standard one because of that
        kept = ButtonSettings.load(broken, defaults=settings)
        self.assertEqual('#ffff00', kept.button_color)

    def test_the_configuration_dialog_hands_the_settings_back(self):
        settings = ButtonSettings(service_name='/mission/patrol', button_text='Patrol',
                                  button_color='#2e7d32', text_color='#ffffff',
                                  error_color='#c62828', response_timeout=4.0, invert_value=True)
        dialog = ButtonSettingsDialog(settings, hold_mode=True)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(settings, dialog.settings())

        dialog._widgets['button_text'].setText('Home')
        dialog._widgets['button_color'].set_color('blue')
        dialog._widgets['text_color'].set_color('')  # back to the color of a standard Qt button
        dialog._widgets['response_timeout'].setValue(1.5)
        dialog._widgets['invert_value'].setChecked(False)
        changed = dialog.settings()
        self.assertEqual('Home', changed.button_text)
        self.assertEqual('#0000ff', changed.button_color)
        self.assertEqual('', changed.text_color)
        self.assertEqual(1.5, changed.response_timeout)
        self.assertFalse(changed.invert_value)
        self.assertEqual(settings.service_name, changed.service_name)

    def test_the_configuration_dialog_asks_only_for_what_the_button_can_use(self):
        for_hold = ButtonSettingsDialog(ButtonSettings(), hold_mode=True)
        self.addCleanup(for_hold.deleteLater)
        self.assertIn('invert_value', for_hold._widgets)
        for_click = ButtonSettingsDialog(ButtonSettings())
        self.addCleanup(for_click.deleteLater)
        self.assertNotIn('invert_value', for_click._widgets)
        # a setting the dialog does not ask for is not made up either
        self.assertFalse(for_click.settings().invert_value)
        self.assertTrue(ButtonSettingsDialog(ButtonSettings(invert_value=True)).settings()
                        .invert_value)

    def test_the_color_to_pick_shows_the_color_itself(self):
        dialog = ButtonSettingsDialog(ButtonSettings(button_color='#2e7d32'), hold_mode=True)
        self.addCleanup(dialog.deleteLater)
        chosen = dialog._widgets['button_color']
        self.assertFalse(chosen._button.icon().isNull())  # a chip of the color, easy to tell apart
        self.assertEqual('#2e7d32', chosen._button.text())
        standard = dialog._widgets['text_color']
        self.assertFalse(standard._button.icon().isNull())
        self.assertEqual('Standard', standard._button.text())

    def test_the_color_of_the_button_is_the_only_color_the_dialog_keeps_to_itself(self):
        # a style sheet set on a widget paints everything inside it as well, which is how picking a
        # color used to repaint the color chooser and all the buttons that came with it
        dialog = ButtonSettingsDialog(ButtonSettings(button_color='#2e7d32'), hold_mode=True)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        self.app.processEvents()
        for widget in [dialog] + dialog.findChildren(QWidget):
            self.assertEqual('', widget.styleSheet(),
                             f'{type(widget).__name__} paints over the look of the Qt style')

    def test_the_standard_look_comes_back_whichever_way_the_color_arrived(self):
        dialog = ButtonSettingsDialog(ButtonSettings(), hold_mode=True)
        self.addCleanup(dialog.deleteLater)
        field = dialog._widgets['button_color']
        self.assertFalse(field._clear.isEnabled())  # there is no color to clear away yet

        field._button.set_color('#2e7d32')  # and this is what the color chooser ends up doing
        self.assertTrue(field._clear.isEnabled())
        self.assertEqual('#2e7d32', field.color())

        field._clear.click()
        self.assertEqual('', field.color())
        self.assertEqual('Standard', field._button.text())
        self.assertFalse(field._clear.isEnabled())
        self.assertEqual('', dialog.settings().button_color)

    def test_the_two_buttons_of_a_color_explain_themselves(self):
        dialog = ButtonSettingsDialog(ButtonSettings(), hold_mode=True)
        self.addCleanup(dialog.deleteLater)
        field = dialog._widgets['button_color']
        self.assertIn('ready to be pressed', field._button.toolTip())  # what the setting means
        # and what the button that clears the color is for
        self.assertIn('Take this color away', field._clear.toolTip())

    def test_the_color_of_a_failed_call_has_no_way_back_to_the_standard_look(self):
        dialog = ButtonSettingsDialog(ButtonSettings(), hold_mode=True)
        self.addCleanup(dialog.deleteLater)
        failure = dialog._widgets['error_color']
        self.assertNotIsInstance(failure, ColorEditor)  # a failed call has to stay visible
        self.assertEqual(ButtonSettings().error_color, failure.color())

    def test_broken_settings_are_ignored(self):
        proxy = SettingsProxy({
            'service_name': '   ',
            'button_text': None,
            'button_color': 'not a color at all',
            'text_color': '#00ff00',
            'error_color': 12345,
            'response_timeout': 'yesterday',
        })
        settings = ButtonSettings.load(proxy)
        defaults = ButtonSettings()
        self.assertEqual(defaults.service_name, settings.service_name)
        self.assertEqual(defaults.button_text, settings.button_text)
        self.assertEqual(defaults.button_color, settings.button_color)
        self.assertEqual('#00ff00', settings.text_color)
        self.assertEqual(defaults.error_color, settings.error_color)
        self.assertEqual(defaults.response_timeout, settings.response_timeout)

    def test_settings_can_be_given_as_arguments(self):
        defaults = ButtonSettings(button_text='Trigger')
        settings, given = ButtonSettings.from_args([
            '--service-name', '/mission/patrol',
            '--button_text', 'Patrol',
            '--button-color', 'red',
            '--response-timeout', '2.5',
            '--invert-value',  # a switch does not need a value of its own
            '--somebody-elses-argument', 'whatever',
        ], defaults=defaults)
        self.assertEqual('/mission/patrol', settings.service_name)
        self.assertEqual('Patrol', settings.button_text)
        self.assertEqual('#ff0000', settings.button_color)
        self.assertEqual(2.5, settings.response_timeout)
        self.assertEqual(defaults.text_color, settings.text_color)
        self.assertTrue(settings.invert_value)
        self.assertEqual({'service_name', 'button_text', 'button_color', 'response_timeout',
                          'invert_value'}, given)

        said_no, _ = ButtonSettings.from_args(
            ['--invert_value', 'false'], defaults=ButtonSettings(invert_value=True))
        self.assertFalse(said_no.invert_value)

        untouched, nothing_given = ButtonSettings.from_args([], defaults=defaults)
        self.assertEqual(defaults, untouched)
        self.assertEqual(set(), nothing_given)


try:
    import launch  # noqa: F401
    import launch_ros  # noqa: F401
    LAUNCH_AVAILABLE = True
except ImportError:
    LAUNCH_AVAILABLE = False


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
        widget = PushButtonWidget(self.gui_node)
        try:
            widget.apply_settings(ButtonSettings(service_name='/button_tests/slow'))
            enabled = False
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not enabled:
                self.process_for(0.05)
                enabled = widget.button.isEnabled()
            self.assertTrue(enabled, 'the button did not notice the service')

            pressed_at = time.monotonic()
            button = widget.button
            QApplication.sendEvent(
                button, QMouseEvent(QEvent.MouseButtonPress, button.rect().center(),
                                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
            took = time.monotonic() - pressed_at
            self.assertLess(took, 0.2, 'pressing the button had to wait for the service')
            self.assertEqual(1, widget.pending_requests())  # the request is on its way

            self.process_for(2.0)
            self.assertEqual([True], [request.data for request in calls])
            self.assertFalse(widget.is_error())
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
        context = PluginContext(self.node, ['--service_name', '/button_tests/patrol',
                                            '--button_text', 'Patrol'])
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
        plugin = CrasRqtPushButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        self.assertIn('(2)', context.widgets[0].windowTitle())
        self.assertIsInstance(context.widgets[0], PushButtonWidget)

    def test_what_is_given_on_the_command_line_wins(self):
        context = PluginContext(self.node, ['--button_text', 'Speak'])
        plugin = CrasRqtPushButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        widget = context.widgets[0]
        stored = SettingsProxy({'button_text': 'Stored in the perspective',
                                'service_name': '/button_tests/home'})
        plugin.restore_settings(None, stored)
        self.assertEqual('Speak', widget.button.text())
        self.assertEqual('/button_tests/home', widget.settings().service_name)

        saved = SettingsProxy()
        plugin.save_settings(None, saved)
        self.assertEqual('Speak', saved.values['button_text'])
        self.assertEqual('/button_tests/home', saved.values['service_name'])

    def test_the_push_button_can_be_inverted_from_the_command_line(self):
        context = PluginContext(self.node, ['--invert-value', 'true'])
        plugin = CrasRqtPushButton(context)
        self.addCleanup(plugin.shutdown_plugin)
        widget = context.widgets[0]
        # what is given on the command line is not lost when the perspective is loaded again
        plugin.restore_settings(None, SettingsProxy({'invert_value': 'False'}))
        self.assertTrue(widget.settings().invert_value)

        stored = PluginContext(self.node, [])
        from_perspective = CrasRqtPushButton(stored)
        self.addCleanup(from_perspective.shutdown_plugin)
        from_perspective.restore_settings(None, SettingsProxy({'invert_value': 'True'}))
        self.assertTrue(stored.widgets[0].settings().invert_value)


@unittest.skipUnless(LAUNCH_AVAILABLE, 'launch and launch_ros are not installed')
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
            ['trigger_button', 'trigger_button', 'push_button', 'trigger_button'],
            [button['executable'] for button in mission_buttons.BUTTONS])

    def test_the_buttons_are_launchable(self):
        mission_buttons = self.load_launch_file()
        buttons = mission_buttons.generate_launch_description().entities
        self.assertEqual(4, len(buttons))
        for button, wanted in zip(buttons, mission_buttons.BUTTONS):
            self.assertEqual('cras_rqt_buttons', button.node_package)
            self.assertEqual(wanted['executable'], button.node_executable)
            arguments = mission_buttons.button_arguments(wanted)
            self.assertEqual(f'/mission/{wanted["service"]}',
                             arguments[arguments.index('--service_name') + 1])


if __name__ == '__main__':
    unittest.main()
