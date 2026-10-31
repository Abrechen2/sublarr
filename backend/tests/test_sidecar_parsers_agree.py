"""The listing parser and the cleanup parser read a sidecar name the same way.

Audit #61 A23: the listing (subtitle_filename) skipped ``.signs`` sidecars and
full-name tags like ``german``, the cleanup (remux) skipped ``.ssa`` — the same
file was visible to one and invisible to the other. The cleanup stays the
stricter of the two on purpose: it never parses a stacked modifier chain or a
backup, because an unparsed sidecar is never trashed.
"""

import pytest

from config_language_data import normalize_language_code
from remux import _parse_sidecar_language
from subtitle_filename import parse_subtitle_filename

BOTH = [
    "Film.de.srt",
    "Film.de.ass",
    "Film.de.ssa",
    "Film.en.forced.srt",
    "Film.de.signs.ass",
    "Film.en.sdh.vtt",
    "Film.german.srt",
    "Film.pt-BR.srt",
    "[Grp] Show - S01E01.ja.ass",
]


@pytest.mark.parametrize("name", BOTH)
def test_both_parsers_name_the_same_language(name):
    base = name.split(".")[0] if not name.startswith("[") else "[Grp] Show - S01E01"
    listed = parse_subtitle_filename(f"/m/{name}")
    cleaned = _parse_sidecar_language(f"/m/{name}", f"/m/{base}")

    assert listed is not None and cleaned is not None
    assert normalize_language_code(listed.language) == normalize_language_code(cleaned)


@pytest.mark.parametrize("name", ["Film.en.hi.forced.srt", "Film.de.bak.srt"])
def test_the_cleanup_leaves_stacks_and_backups_alone(name):
    assert _parse_sidecar_language(f"/m/{name}", "/m/Film") is None


def test_a_signs_sidecar_is_listed_with_its_badge(tmp_path):
    from services.sidecar_scan import scan_subtitle_sidecars

    (tmp_path / "Film.mkv").write_bytes(b"")
    (tmp_path / "Film.de.signs.ass").write_bytes(b"x")

    [entry] = scan_subtitle_sidecars(str(tmp_path / "Film.mkv"))

    assert entry["language"] == "de"
    assert entry["modifier"] == "signs"
