"""Vendored third-party libraries for Sublarr.

At import time this package inserts its own directory into sys.path[0] so
that the sibling packages (e.g. subliminal/, babelfish/) are importable as
top-level modules — the same pattern Bazarr uses for its libs/ directory.

Vendored packages live alongside this file, one directory per package.
See VENDOR_PATCHES.md for source commit SHAs and applied patches.
"""

import os
import sys

_VENDOR_DIR = os.path.dirname(os.path.abspath(__file__))
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)
