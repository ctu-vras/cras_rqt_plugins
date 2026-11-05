# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Standalone launcher of the PTZ control plugin."""

import sys

from rqt_gui.main import Main


def main():
    """Start RQt with the PTZ control plugin only."""
    main = Main()
    sys.exit(main.main(sys.argv, standalone='cras_rqt_ptz_control.ptz_control.PtzControl'))


if __name__ == '__main__':
    main()
