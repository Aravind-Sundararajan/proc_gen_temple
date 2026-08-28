"""Parametric Dravidian gopuram generator for 3D printing: the mandapa's sister app.

The gopuram is the gateway tower of the enclosure wall — an oblong masonry base with
the processional passage through it, diminishing brick talas above, and the barrel-
vaulted sala sikhara with its row of kalasas on top.  This package supplies what is
*of the gopuram* — the parameters, the builder, the presets, the ``<gopuram>`` format
binding, the two entry points — and stands on :mod:`mandapa` for everything a building
is not: the mesh kit, the ornament, the union and reports, the document machinery, the
editor shell.  The dependency runs one way, gopuram → mandapa, and
``tests/test_dependency_rule.py`` holds that line.
"""

__version__ = "0.1.0"
