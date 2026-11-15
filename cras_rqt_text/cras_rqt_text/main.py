# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Standalone launcher of the text plugin."""


def main():
    """Start the plugin in a window of its own."""
    import sys

    from cras_rqt_text.text_settings import TextSettings
    from rqt_gui.main import Main

    main = Main()
    sys.exit(main.main(
        sys.argv, standalone='cras_rqt_text/Text', plugin_argument_provider=TextSettings.add_arguments))
