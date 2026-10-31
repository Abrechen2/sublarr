"""A sidecar belongs to the video whose stem it carries, not to a prefix of it.

Audit #61 A20: ``Film.*`` also matched ``Film.Extended.en.srt``, so the listing
of ``Film.mkv`` showed the Extended cut's subtitle and bulk sync timed it
against the wrong video.
"""

from services.sidecar_scan import scan_subtitle_sidecars


def _touch(path):
    path.write_bytes(b"x")
    return str(path)


def test_the_longer_cuts_sidecars_stay_with_the_longer_cut(tmp_path):
    film = _touch(tmp_path / "Film.mkv")
    extended = _touch(tmp_path / "Film.Extended.mkv")
    own = _touch(tmp_path / "Film.de.srt")
    other = _touch(tmp_path / "Film.Extended.en.srt")
    other_combined = _touch(tmp_path / "Film.Extended.de-en.combined.ass")
    own_combined = _touch(tmp_path / "Film.de-en.combined.ass")

    assert {e["path"] for e in scan_subtitle_sidecars(film)} == {own, own_combined}
    assert {e["path"] for e in scan_subtitle_sidecars(extended)} == {other, other_combined}


def test_brackets_and_modifiers_still_match(tmp_path):
    video = _touch(tmp_path / "[Grp] Show - S01E01.mkv")
    hi = _touch(tmp_path / "[Grp] Show - S01E01.en.hi.srt")

    [entry] = scan_subtitle_sidecars(video)

    assert entry["path"] == hi
    assert entry["modifier"] == "hi"
