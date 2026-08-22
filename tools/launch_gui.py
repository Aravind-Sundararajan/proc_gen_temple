"""PyInstaller entry point for the editor: the call the ``temple-gen`` console script makes.

PyInstaller wants a script, not an entry point, and a script that lives outside the package
keeps the package free of any notion of being frozen.
"""

import sys

from mandapa.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
