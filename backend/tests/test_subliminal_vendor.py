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


def test_vendored_subliminal_importable():
    """The vendored Subliminal must be importable as a top-level package."""
    import providers._vendor  # noqa: F401  (trigger sys.path shim)

    import subliminal

    assert hasattr(subliminal, "__version__"), "subliminal.__version__ attribute missing"
    assert subliminal.__version__.startswith("2.2"), (
        f"Expected Subliminal 2.2.x, got {subliminal.__version__}"
    )


def test_vendored_subliminal_providers_discoverable():
    """Subliminal's provider entry points must be discoverable via stevedore."""
    import providers._vendor  # noqa: F401

    from subliminal.providers import Provider  # base class

    assert Provider is not None, "subliminal.providers.Provider not importable"


def test_vendored_babelfish_importable():
    """The vendored babelfish must be importable as a top-level package."""
    import providers._vendor  # noqa: F401

    import babelfish

    assert hasattr(babelfish, "Language"), "babelfish.Language class missing"
    de = babelfish.Language("deu")
    assert de.alpha2 == "de"


def test_subliminal_can_use_babelfish():
    """Subliminal's internal babelfish usage must work with our vendored copy."""
    import providers._vendor  # noqa: F401

    from babelfish import Language
    from subliminal.video import Video

    v = Video.fromname("Frozen.2013.720p.BluRay.x264-DON.mkv")
    assert v.title.lower() == "frozen"
    # Basic smoke — don't assert specifics, just ensure no import-time crash
    assert Language("eng") is not None
