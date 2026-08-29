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


def _configure_subliminal_cache() -> None:
    """Configure the vendored Subliminal cache region.

    ``subliminal/cache.py`` builds ``region = make_region(...)`` at import and
    only ever configures it inside ``cli.py`` — Subliminal's own command-line
    entry point, which Sublarr never runs. An unconfigured dogpile region
    raises from its internals on first use, so every provider that decorates a
    method with ``@region.cache_on_arguments`` failed 100% of its searches
    (addic7ed and tvsubtitles are the only two that do).

    Memory backend on purpose: the cache holds show-id lookups, it is a
    latency optimisation and not state worth persisting across restarts.
    """
    try:
        from subliminal.cache import region

        if not region.is_configured:
            region.configure("dogpile.cache.memory")
    except Exception:  # pragma: no cover — never let a cache break imports
        import logging

        logging.getLogger(__name__).debug(
            "could not configure the vendored subliminal cache region", exc_info=True
        )


_configure_subliminal_cache()
