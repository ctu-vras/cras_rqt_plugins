# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Standalone launcher of the PTZ control plugin."""


def main():
    import sys

    from cras_rqt_ptz_control.ptz_control_settings import PtzControlSettings
    from rqt_gui.main import Main

    main = Main()
    sys.exit(main.main(
        sys.argv, standalone='cras_rqt_ptz_control/PtzControl',
        plugin_argument_provider=PtzControlSettings.add_arguments))
