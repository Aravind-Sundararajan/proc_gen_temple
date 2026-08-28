"""PyInstaller entry point for the gopuram editor: the call the ``gopuram-gen`` console
script makes.  Outside the package for the same reason as ``launch_gui.py``."""

import sys

from gopuram.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
