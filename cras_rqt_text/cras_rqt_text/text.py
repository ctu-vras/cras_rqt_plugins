# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""RQt plugin showing a text coming from a ROS topic."""

from cras_rqt_common.settings_plugin import SettingsPlugin
from cras_rqt_text.text_widget import TextWidget


class Text(SettingsPlugin[TextWidget]):
    """
    An RQt plugin showing a text coming from a std_msgs/String or OverlayText topic.

    The topic, the message type and the text appearance are configured through the standard RQt
    configuration dialog, opened by a gear button in the dock title bar or in the widget corner, and
    they can be given on the command line as options named after them.
    """

    def __init__(self, context, plugin_name: str = 'Text'):
        super().__init__(context, plugin_name)
