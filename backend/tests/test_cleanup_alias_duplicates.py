"""alias_duplicates rule: X.deu.srt beside an identical X.de.srt goes to the trash.

Prod case: 12 episodes had ``X.de.srt`` and ``X.deu.srt`` side by side with the
same subtitle, so Emby listed two German tracks.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from services.cleanup_alias_duplicates import execute_alias_duplicates

_CUES = [(1000 * i, 1000 * i + 800, f"Line number {i}") for i in range(1, 51)]


def _srt(cues=_CUES, *, newline="\n", bom=False, trailing=""):
    def ts(ms):
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, milli = divmod(rem, 1000)
        return f"{h:02}:{m:02}:{s:02},{milli:03}"

    body = "".join(
        f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n\n" for i, (a, b, text) in enumerate(cues, 1)
    )
    body = body.replace("\n", newline) + trailing
    return ("﻿" if bom else "") + body


def _write(tmp_path, name, content):
    (tmp_path / name).write_bytes(content.encode("utf-8"))


def _run(tmp_path, dry_run=False):
    with patch("services.media_server_notify.notify_media_servers_batch") as notify:
        result = execute_alias_duplicates(str(tmp_path), {}, dry_run=dry_run)
    return result, notify


def _files(tmp_path):
    return {p.name for p in tmp_path.iterdir() if p.is_file()}


def test_identical_alias_is_trashed_and_recoverable(tmp_path):
    (tmp_path / "v.mkv").write_bytes(b"x")
    _write(tmp_path, "v.de.srt", _srt())
    _write(tmp_path, "v.deu.srt", _srt())

    result, notify = _run(tmp_path)

    assert _files(tmp_path) == {"v.mkv", "v.de.srt"}
    assert result["deleted"] == 1
    manifest = tmp_path / ".sublarr_trash" / result["batch_id"] / "manifest.json"
    entry = json.loads(manifest.read_text())["files"][0]
    assert entry["original"].endswith("v.deu.srt")
    assert (tmp_path / ".sublarr_trash" / result["batch_id"] / "v.deu.srt").exists()
    notify.assert_called_once_with([str(tmp_path / "v.mkv")])


def test_trivial_differences_still_count_as_same(tmp_path):
    _write(tmp_path, "v.de.srt", _srt())
    _write(tmp_path, "v.ger.srt", _srt(newline="\r\n", bom=True, trailing="\r\n\r\n"))

    result, _ = _run(tmp_path)

    assert result["deleted"] == 1
    assert _files(tmp_path) == {"v.de.srt"}


def test_one_changed_cue_in_fifty_is_within_tolerance(tmp_path):
    changed = [*_CUES[:-1], (_CUES[-1][0], _CUES[-1][1], "Something else")]
    _write(tmp_path, "v.de.srt", _srt())
    _write(tmp_path, "v.deu.srt", _srt(changed))

    assert _run(tmp_path)[0]["deleted"] == 1


def test_different_content_keeps_both(tmp_path):
    other = [(a, b, f"Andere Zeile {i}") for i, (a, b, _) in enumerate(_CUES)]
    _write(tmp_path, "v.de.srt", _srt())
    _write(tmp_path, "v.deu.srt", _srt(other))

    result, notify = _run(tmp_path)

    assert result["deleted"] == 0
    assert _files(tmp_path) == {"v.de.srt", "v.deu.srt"}
    notify.assert_not_called()


def test_only_alias_present_is_kept(tmp_path):
    _write(tmp_path, "v.deu.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 0
    assert _files(tmp_path) == {"v.deu.srt"}


def test_english_alias(tmp_path):
    _write(tmp_path, "v.en.srt", _srt())
    _write(tmp_path, "v.eng.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 1
    assert _files(tmp_path) == {"v.en.srt"}


def test_two_aliases_of_one_canonical_both_go(tmp_path):
    for name in ("v.de.srt", "v.deu.srt", "v.ger.srt"):
        _write(tmp_path, name, _srt())

    assert _run(tmp_path)[0]["deleted"] == 2
    assert _files(tmp_path) == {"v.de.srt"}


def test_forced_pairs_only_with_forced(tmp_path):
    # Same bytes everywhere, but the full alias has no full canonical peer.
    _write(tmp_path, "v.de.forced.srt", _srt())
    _write(tmp_path, "v.deu.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 0
    assert _files(tmp_path) == {"v.de.forced.srt", "v.deu.srt"}

    _write(tmp_path, "v.deu.forced.srt", _srt())
    assert _run(tmp_path)[0]["deleted"] == 1
    assert _files(tmp_path) == {"v.de.forced.srt", "v.deu.srt"}


def test_other_format_is_not_a_duplicate(tmp_path):
    _write(tmp_path, "v.de.ass", "[Script Info]\n")
    _write(tmp_path, "v.deu.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 0


def test_other_video_is_not_paired(tmp_path):
    _write(tmp_path, "a.de.srt", _srt())
    _write(tmp_path, "b.deu.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 0


def test_empty_canonical_does_not_justify_trashing(tmp_path):
    _write(tmp_path, "v.de.srt", "")
    _write(tmp_path, "v.deu.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 0
    assert _files(tmp_path) == {"v.de.srt", "v.deu.srt"}


def test_brazilian_portuguese_variant_is_not_an_alias(tmp_path):
    _write(tmp_path, "v.pt.srt", _srt())
    _write(tmp_path, "v.pob.srt", _srt())

    assert _run(tmp_path)[0]["deleted"] == 0


def test_dry_run_touches_nothing(tmp_path):
    _write(tmp_path, "v.de.srt", _srt())
    _write(tmp_path, "v.deu.srt", _srt())

    result, notify = _run(tmp_path, dry_run=True)

    assert result["would_delete"] == 1
    assert result["examples"][0]["path"].endswith("v.deu.srt")
    assert _files(tmp_path) == {"v.de.srt", "v.deu.srt"}
    notify.assert_not_called()


def test_rule_is_seeded_enabled(app_ctx):
    from db.repositories.cleanup import CleanupRepository

    rule = next(r for r in CleanupRepository().get_rules() if r["rule_type"] == "alias_duplicates")
    assert rule["enabled"] is True
    assert rule["schedule"] == "daily"


def _episode(n=345):
    return [
        (12000 + 4000 * i, 12000 + 4000 * i + 1400, f"Synthetic line {i} of text") for i in range(n)
    ]


def test_prod_shape_shifted_timing_and_split_lines_is_same(tmp_path):
    """Prod pairs: every cue ~0.12 s earlier in one file, a few lines split or added."""
    base = _episode()
    shifted = [(a - 120, b - 120, t) for a, b, t in base]
    for i in (10, 100, 200):  # split three lines in two halves
        a, b, t = shifted[i]
        words = t.split(" ")
        mid = (a + b) // 2
        shifted[i] = (a, mid, " ".join(words[:3]))
        shifted.append((mid, b, " ".join(words[3:])))
    shifted.append((1000, 2000, "An added line"))
    shifted.sort()
    _write(tmp_path, "v.de.srt", _srt(base))
    _write(tmp_path, "v.deu.srt", _srt(shifted))

    assert _run(tmp_path)[0]["deleted"] == 1
    assert _files(tmp_path) == {"v.de.srt"}


def test_same_timing_other_translation_is_different(tmp_path):
    base = _episode()
    other = [(a, b, f"Ganz andere Uebersetzung {i}") for i, (a, b, _) in enumerate(base)]
    _write(tmp_path, "v.de.srt", _srt(base))
    _write(tmp_path, "v.deu.srt", _srt(other))

    assert _run(tmp_path)[0]["deleted"] == 0


def test_same_texts_but_far_offset_is_different(tmp_path):
    base = _episode()
    _write(tmp_path, "v.de.srt", _srt(base))
    _write(tmp_path, "v.deu.srt", _srt([(a + 5000, b + 5000, t) for a, b, t in base]))

    assert _run(tmp_path)[0]["deleted"] == 0
