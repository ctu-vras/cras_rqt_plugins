# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

"""Standalone launcher of the text plugin."""

import sys

from rqt_gui.main import Main


def main():
    """Start RQt with the text plugin only."""
    main = Main()
    sys.exit(main.main(sys.argv, standalone='cras_rqt_text.text.Text'))


if __name__ == '__main__':
    main()
