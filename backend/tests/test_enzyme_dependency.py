"""enzyme stays installed (GitHub #183, bug 7).

subliminal's "metadata" refiner imports enzyme through a registered entry
point; without it every start logged an ERROR. It must stay declared and
importable.
"""

import re
from pathlib import Path


def test_enzyme_is_pinned_in_requirements():
    requirements = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    assert re.search(r"^enzyme==", requirements, re.MULTILINE)


def test_enzyme_imports():
    import enzyme  # noqa: F401
