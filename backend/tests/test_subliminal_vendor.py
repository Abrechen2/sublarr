"""Smoke tests for the vendored Subliminal + babelfish packages."""

import sys
from pathlib import Path


def test_vendor_directory_added_to_sys_path():
    """Importing providers._vendor must inject the vendor dir into sys.path."""
    import providers._vendor  # noqa: F401  (side-effect import)

    vendor_dir = str(Path(providers._vendor.__file__).parent)
    assert vendor_dir in sys.path, (
        f"Expected {vendor_dir} in sys.path after import; got {sys.path[:5]}..."
    )
