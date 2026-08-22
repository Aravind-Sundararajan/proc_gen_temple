"""PyInstaller entry point for the headless command: the call the ``mandapa`` console script makes."""

import sys

from mandapa.cli import main

if __name__ == "__main__":
    sys.exit(main())
