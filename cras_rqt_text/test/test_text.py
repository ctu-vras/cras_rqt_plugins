# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Tests of the RQt plugin showing a text coming from a ROS topic."""

import os
import time

if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    # The tests build real widgets, and a headless machine has no screen to build them on.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from cras_rqt_text.text_frame import build_frame, MAX_PREFERRED_SIZE, scaling_factor  # noqa: E402
from cras_rqt_text.text_frame import TextFrame  # noqa: E402
from cras_rqt_text.text_html import build_html, css_color, markup  # noqa: E402
from cras_rqt_text.text_settings import (BOTTOM, CENTER, format_color, LEFT,  # noqa: E402
                                         OVERLAY_TYPE, parse_color, RIGHT, STRING_TYPE,
                                         TextSettings, TOP)
from cras_rqt_text.text_settings_dialog import TextSettingsDialog  # noqa: E402
from cras_rqt_text.text_widget import TextWidget  # noqa: E402
import pytest  # noqa: E402
from python_qt_binding.QtGui import QColor, QImage, QTextDocument  # noqa: E402
from python_qt_binding.QtWidgets import QApplication  # noqa: E402
import rclpy  # noqa: E402
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy  # noqa: E402
from rviz_2d_overlay_msgs.msg import OverlayText  # noqa: E402
from std_msgs.msg import ColorRGBA, String  # noqa: E402

BEST_EFFORT = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT,
                         durability=QoSDurabilityPolicy.VOLATILE)
# Something published before the plugin started has to be heard too.
LATCHED = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
                     durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)

RED = QColor(255, 0, 0, 255)
BLACK = QColor(0, 0, 0, 255)
GREEN = QColor(0, 255, 0, 255)
GREEN_BG = ColorRGBA(g=1.0, a=1.0)


class SettingsProxy:
    """A stand-in for the settings proxy rqt hands to the plugins."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, name, default=None):
        return self.values.get(name, default)

    def set_value(self, name, value):
        self.values[name] = value


class Spinning:
    """
    A node the widgets can talk through, spun by hand.

    :meth:`spin` interleaves spinning the node and processing the GUI events, so nothing runs in
    parallel and every test sees the messages in the order it triggers them.
    """

    def __init__(self):
        rclpy.init(args=['cras_rqt_text_tests'])
        self.node = Node('cras_rqt_text_tests')
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.app = QApplication.instance() or QApplication([])
        self.widgets = []

    def close(self) -> None:
        for widget in self.widgets:
            widget.shutdown()
        self.executor.shutdown()
        self.node.destroy_node()
        rclpy.shutdown()

    def spin(self, duration: float = 0.0) -> None:
        deadline = time.monotonic() + duration
        while True:
            self.executor.spin_once(timeout_sec=0.0)
            self.app.processEvents()
            if time.monotonic() >= deadline:
                return

    def spin_until(self, condition, timeout: float = 10.0) -> bool:
        """Spin until the condition holds, and tell whether it ever did."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            self.spin(0.02)
        return bool(condition())

    def publish_until(self, publisher, message, condition, timeout: float = 10.0) -> bool:
        """
        Keep publishing a message until the condition holds.

        A publisher that is only discovered after the first message was sent would otherwise miss
        it, which is nothing a test wants to tell apart from a broken plugin.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            publisher.publish(message)
            if condition():
                return True
            self.spin(0.05)
        publisher.publish(message)
        return bool(condition())


@pytest.fixture(scope='module')
def spinning():
    world = Spinning()
    yield world
    world.close()


def overlay_message(**changes):
    """Build an OverlayText message with the given fields set, the rest in its defaults."""
    message = OverlayText()
    message.text = 'the text'
    message.fg_color = ColorRGBA(r=1.0, a=0.5)
    message.bg_color = GREEN_BG
    message.text_size = 30.0
    message.font = 'Monospace'
    message.horizontal_alignment = RIGHT
    message.vertical_alignment = BOTTOM
    message.horizontal_distance = 7
    message.vertical_distance = 9
    message.width = 222
    message.height = 111
    for name, value in changes.items():
        setattr(message, name, value)
    return message


def make_widget(world: Spinning, **settings) -> TextWidget:
    """
    Build a widget configured the way the settings ask for, resized to have something to see.

    An empty ``topic`` keeps it from subscribing to anything, which is what the tests that only
    paint need.
    """
    widget = TextWidget(world.node)
    world.widgets.append(widget)  # keep it alive, it listens on the shared node
    values = {'topic': ''}
    values.update(settings)
    widget.restore_settings(None, SettingsProxy(values))
    widget.resize(240, 90)
    return widget


def received(widget: TextWidget):
    """Report the message the widget has heard, or ``None`` while the default text is shown."""
    return widget._message


def shown(widget: TextWidget):
    """Tell what the widget shows right now."""
    return widget._frame()


def painted(widget: TextWidget) -> QImage:
    """Grab what the widget paints."""
    image = QImage(widget.width(), widget.height(), QImage.Format_ARGB32)
    image.fill(QColor('magenta'))
    widget.render(image)
    return image


def sampled(image: QImage, top: int = 0, bottom=None):
    """Sample the colors on a grid over the painted image, so that text on it is found in it."""
    bottom = image.height() if bottom is None else min(bottom, image.height())
    for y in range(top, bottom, 3):
        for x in range(0, image.width(), 3):
            yield image.pixelColor(x, y)


def inked(image: QImage, background: QColor, top: int = 0, bottom=None) -> bool:
    """Whether some sampled pixel between the given rows is not the given background color."""
    return any(color != background for color in sampled(image, top, bottom))


def test_defaults_listen_for_plain_strings():
    settings = TextSettings()
    assert settings.topic
    assert settings.message_type == STRING_TYPE
    assert not settings.overlay_messages
    assert settings.default_text


def test_settings_survive_a_round_through_rqt_settings():
    settings = TextSettings(topic='my/text', message_type=OVERLAY_TYPE, default_text='hello',
                            text_size_pt=42.0, scale_with_widget=True, reference_height=480,
                            text_color=(1, 2, 3, 4), background_color=(5, 6, 7, 8),
                            horizontal_alignment=CENTER, vertical_alignment=BOTTOM,
                            take_style_from_message=False, take_background_from_message=False,
                            take_layout_from_message=False)
    proxy = SettingsProxy()
    settings.save(proxy)
    assert proxy.values['text_color'] == '#01020304'
    assert TextSettings.load(proxy) == settings


def test_an_empty_topic_stays_empty_but_junk_falls_back():
    junk = {'topic': '', 'message_type': 'std_srvs/srv/SetBool', 'text_size_pt': 'wide',
            'reference_height': 5, 'text_color': 'burundy', 'horizontal_alignment': 17,
            'take_style_from_message': 'false'}
    settings = TextSettings.load(SettingsProxy(junk))
    assert settings.topic == ''
    assert settings.message_type == STRING_TYPE
    assert settings.text_size_pt == TextSettings().text_size_pt
    assert settings.reference_height == 10
    assert settings.text_color == TextSettings().text_color
    assert settings.horizontal_alignment == LEFT
    assert not settings.take_style_from_message


@pytest.mark.parametrize('given, expected', [
    ('#f09', (255, 0, 153, 255)),
    ('#112233', (17, 34, 51, 255)),
    ('#112233ff', (17, 34, 51, 255)),
    ('#11223300', (17, 34, 51, 0)),
    ((10, 20, 30), (10, 20, 30, 255)),
    ('burundy', (9, 9, 9, 9)),
])
def test_colors_have_one_text_form(given, expected):
    assert parse_color(given, (9, 9, 9, 9)) == expected
    assert parse_color(format_color(expected), (0, 0, 0, 0)) == expected


def test_a_color_left_unset_is_kept_unset_through_a_round_and_shows_no_color():
    settings = TextSettings()
    assert settings.text_color is None
    assert settings.background_color is None
    proxy = SettingsProxy()
    settings.save(proxy)
    assert proxy.values['text_color'] == ''
    assert TextSettings.load(proxy) == settings
    assert parse_color('', None) is None
    assert parse_color(None, None) is None
    assert 'color' not in build_html(TextFrame(text='text'))


def test_the_markup_of_the_text_survives_and_a_stray_bracket_does_not_eat_it():
    assert markup('3 < 5 and <b>bold</b>') == '3 &lt; 5 and <b>bold</b>'
    assert markup('one\ntwo\r\nthree') == 'one<br/>two<br/>three'
    assert markup('<font color="#00ff00">green</font>') == '<font color="#00ff00">green</font>'


def test_the_alpha_of_a_color_goes_to_css():
    assert css_color((255, 0, 0, 128)) == 'rgba(255, 0, 0, 0.502)'


def test_the_style_of_the_text_leaves_room_for_the_style_of_the_message():
    html = build_html(TextFrame(text='hi <big>there</big>', color=(1, 2, 3, 255), size_pt=24.5,
                                font='Monospace', horizontal_alignment=CENTER))
    assert 'font-size: 24.5pt' in html
    assert "font-family: 'Monospace'" in html
    assert 'text-align: center' in html
    assert html.endswith('hi <big>there</big></div>')
    assert 'font-family' not in build_html(TextFrame(text='hi'))


def test_a_string_is_shown_with_the_configured_appearance():
    settings = TextSettings(text_size_pt=20.0, text_color=(1, 2, 3, 255),
                            background_color=(4, 5, 6, 255), horizontal_alignment=RIGHT,
                            vertical_alignment=BOTTOM)
    frame = build_frame(settings, 'a string', 100)
    assert frame.text == 'a string'
    assert (frame.color, frame.background) == ((1, 2, 3, 255), (4, 5, 6, 255))
    assert (frame.horizontal_alignment, frame.vertical_alignment) == (RIGHT, BOTTOM)
    assert frame.size_pt == 20.0


def test_a_text_without_colors_of_its_own_asks_for_the_ones_rqt_uses():
    frame = build_frame(TextSettings(), 'a string', 100)
    assert (frame.color, frame.background) == (None, None)


def test_the_default_text_is_shown_before_anything_arrives():
    assert build_frame(TextSettings(default_text='waiting'), None, 100).text == 'waiting'


def test_the_text_grows_with_the_widget_only_when_asked_for():
    settings = TextSettings(text_size_pt=10.0, scale_with_widget=True, reference_height=200)
    assert scaling_factor(settings, 200) == 1.0
    assert scaling_factor(settings, 600) == 3.0
    assert scaling_factor(settings, 0) == 1.0
    assert build_frame(settings, 'text', 600).size_pt == 30.0
    assert build_frame(TextSettings(text_size_pt=10.0), 'text', 600).size_pt == 10.0


def test_an_overlay_text_bring_its_own_appearance_and_place():
    frame = build_frame(TextSettings(), overlay_message(), 100)
    assert frame.text == 'the text'
    assert frame.color == (255, 0, 0, 128)
    assert frame.background == (0, 255, 0, 255)
    assert frame.size_pt == 30.0
    assert frame.font == 'Monospace'
    assert (frame.horizontal_alignment, frame.vertical_alignment) == (RIGHT, BOTTOM)
    assert (frame.horizontal_distance, frame.vertical_distance) == (7, 9)
    assert (frame.preferred_width, frame.preferred_height) == (222, 111)


def test_an_overlay_text_can_be_told_to_obey_the_settings():
    settings = TextSettings(text_size_pt=20.0, text_color=(1, 2, 3, 255),
                            background_color=(4, 5, 6, 255), horizontal_alignment=LEFT,
                            vertical_alignment=TOP, take_style_from_message=False,
                            take_background_from_message=False, take_layout_from_message=False)
    frame = build_frame(settings, overlay_message(), 100)
    assert frame.text == 'the text'
    assert frame.size_pt == 20.0
    assert frame.font == ''
    assert frame.color == (1, 2, 3, 255)
    assert frame.background == (4, 5, 6, 255)
    assert (frame.horizontal_alignment, frame.vertical_alignment) == (LEFT, TOP)
    assert (frame.preferred_width, frame.preferred_height) == (0, 0)


def test_an_overlay_text_without_a_size_of_its_own_keeps_the_configured_one():
    frame = build_frame(TextSettings(text_size_pt=20.0), overlay_message(text_size=0.0), 100)
    assert frame.size_pt == 20.0


def test_an_overlay_text_cannot_ask_for_an_absurd_room():
    frame = build_frame(TextSettings(), overlay_message(width=100000, height=-5), 100)
    assert frame.preferred_width == MAX_PREFERRED_SIZE
    assert frame.preferred_height == 0


def test_deleting_an_overlay_text_hides_it():
    assert build_frame(TextSettings(), overlay_message(action=OverlayText.DELETE), 100) is None


def test_qt_shows_the_markup_of_the_text(spinning):
    document = QTextDocument()
    document.setHtml(build_html(TextFrame(text='plain <b>bold</b><br/>second <b>line</b>')))
    assert document.toPlainText() == 'plain bold\nsecond line'


def test_qt_shows_the_configured_style_of_the_text(spinning):
    document = QTextDocument()
    document.setHtml(build_html(TextFrame(text='text', color=(255, 0, 0, 255), size_pt=30.0,
                                          font='Monospace')))
    style = document.firstBlock().charFormat()
    assert style.fontPointSize() == 30.0
    assert (style.foreground().color().red(), style.foreground().color().green()) == (255, 0)
    assert document.idealWidth() > 0


def test_qt_wraps_a_text_that_does_not_fit(spinning):
    document = QTextDocument()
    document.setHtml(build_html(TextFrame(text='a text that is much longer than the widget is')))
    document.setTextWidth(40)
    assert document.size().width() <= 40.0
    assert document.size().height() > 30.0


def test_qt_leaves_the_markup_of_a_message_alone(spinning):
    document = QTextDocument()
    document.setHtml(build_html(build_frame(TextSettings(), overlay_message(
        text='size <font size="20">here</font> and <u>underlined</u>'), 100)))
    assert document.toPlainText() == 'size here and underlined'


def test_the_widget_falls_back_to_the_colors_of_any_rqt_widget(spinning):
    widget = make_widget(spinning, default_text='waiting for text')
    standard = widget._standard_colors()
    background = QColor(*standard['background_color'])
    image = painted(widget)
    assert image.pixelColor(image.width() - 2, image.height() - 2) == background
    assert shown(widget).color == standard['text_color']
    assert inked(image, background)


def test_the_settings_dialog_keeps_the_colors_it_was_given(spinning):
    widget = make_widget(spinning, default_text='waiting for text')
    dialog = TextSettingsDialog(widget._settings, widget, widget._standard_colors())
    assert dialog.settings() == widget._settings


def test_the_settings_dialog_can_go_back_to_the_standard_colors(spinning):
    widget = make_widget(spinning, default_text='waiting for text')
    dialog = TextSettingsDialog(widget._settings, widget, widget._standard_colors())
    color = dialog._widgets['text_color']
    assert 'standard' in color._swatch.text()
    assert not color._standard_button.isEnabled()
    color._color = (10, 20, 30, 255)
    color._show_color()
    assert dialog.settings().text_color == (10, 20, 30, 255)
    assert color._standard_button.isEnabled()
    color._use_standard_color()
    assert dialog.settings().text_color is None


def test_the_default_text_is_painted_over_the_configured_background(spinning):
    widget = make_widget(spinning, default_text='waiting for text', background_color='#ff0000')
    image = painted(widget)
    assert image.pixelColor(image.width() - 2, image.height() - 2) == RED
    assert inked(image, RED)


def test_nothing_but_the_background_is_painted_without_a_text(spinning):
    widget = make_widget(spinning, default_text='', background_color='#ff0000')
    assert not inked(painted(widget), RED)


def test_the_text_is_shown_where_the_settings_ask_for(spinning):
    # A dark background needs a light text, the standard text color being meant for the standard
    # background of a widget.
    widget = make_widget(spinning, default_text='', background_color='#000000',
                         text_color='#ffffff', vertical_alignment=TOP)
    widget._engine.string_text.emit('one line')
    image = painted(widget)
    assert inked(image, BLACK, bottom=image.height() // 2)
    assert not inked(image, BLACK, top=image.height() // 2)
    widget = make_widget(spinning, default_text='', background_color='#000000',
                         text_color='#ffffff', vertical_alignment=BOTTOM)
    widget._engine.string_text.emit('one line')
    image = painted(widget)
    assert not inked(image, BLACK, bottom=image.height() // 2)
    assert inked(image, BLACK, top=image.height() // 2)


def test_a_string_published_on_the_topic_is_shown(spinning):
    widget = make_widget(spinning, topic='cras_rqt_text_tests/string')
    publisher = spinning.node.create_publisher(String, '/cras_rqt_text_tests/string', BEST_EFFORT)
    arrived = spinning.publish_until(publisher, String(data='a <b>string</b>'),
                                     lambda: received(widget) is not None)
    assert arrived
    assert shown(widget).text == 'a <b>string</b>'
    assert inked(painted(widget), QColor(*widget._frame().background))


def test_a_latched_overlay_text_published_early_is_shown(spinning):
    publisher = spinning.node.create_publisher(OverlayText, '/cras_rqt_text_tests/overlay',
                                               LATCHED)
    spinning.spin(0.2)
    publisher.publish(overlay_message(text='latched <b>text</b>'))
    widget = make_widget(spinning, topic='cras_rqt_text_tests/overlay', message_type=OVERLAY_TYPE,
                         default_text='')
    assert spinning.spin_until(lambda: received(widget) is not None)
    assert shown(widget).text == 'latched <b>text</b>'
    assert inked(painted(widget), GREEN)


def test_deleting_an_overlay_text_stops_painting_it(spinning):
    widget = make_widget(spinning, topic='cras_rqt_text_tests/deleting',
                         message_type=OVERLAY_TYPE, default_text='')
    publisher = spinning.node.create_publisher(OverlayText, '/cras_rqt_text_tests/deleting',
                                               LATCHED)
    assert spinning.publish_until(publisher, overlay_message(),
                                  lambda: received(widget) is not None)
    assert inked(painted(widget), GREEN)
    assert spinning.publish_until(publisher, overlay_message(action=OverlayText.DELETE),
                                  lambda: shown(widget) is None)
    assert all(color != GREEN for color in sampled(painted(widget)))


def test_the_widget_asks_for_the_room_the_overlay_text_wants(spinning):
    widget = make_widget(spinning, topic='cras_rqt_text_tests/room', message_type=OVERLAY_TYPE)
    publisher = spinning.node.create_publisher(OverlayText, '/cras_rqt_text_tests/room', LATCHED)
    assert spinning.publish_until(publisher, overlay_message(width=321, height=123),
                                  lambda: widget.sizeHint().width() == 321)
    assert widget.sizeHint().height() == 123
