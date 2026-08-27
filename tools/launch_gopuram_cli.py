"""PyInstaller entry point for the gopuram headless command: the ``gopuram`` console script."""

import sys

from gopuram.cli import main

if __name__ == "__main__":
    sys.exit(main())
