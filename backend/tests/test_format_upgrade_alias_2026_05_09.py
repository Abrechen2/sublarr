"""Regression tests for the 2026-05-09 format_upgrade alias-aware fix.

User-reported (Akame ga Kill! S01E06): Sublarr's library showed 2
subtitle tracks while Emby showed 4. Investigation surfaced that
``Show.de.ass`` and ``Show.ger.srt`` are both German (``ger`` is the
ISO-639-2 alias for ``de``), but ``execute_format_upgrade`` indexed
files by ``(dirpath, base_without_ext)`` so the two never landed in
the same bucket — the redundant ``.ger.srt`` stayed on disk forever.

Cross-checked design with Gemini cold-review (2026-05-09). Critical
edge case caught: grouping ONLY by ``(video_base, canonical_lang)``
would let ``Show.de.forced.srt`` collapse with ``Show.de.ass`` and
get trashed as inferior. Forced/SDH/HI subs are SEPARATE tracks, not
lower-quality versions of the main track. Fix: include ``modifier``
in the grouping key.

Tests below exercise:
- ISO alias resolution (``ger`` ↔ ``de``)
- Modifier protection (``forced`` / ``sdh`` / ``hi`` / ``cc``)
- Untagged sidecar preservation (audit C1-1)
- Multiple inferior peers under the same logical track all get trashed
- Single inferior with no preferred peer is kept
"""

from __future__ import annotations

import os

import pytest


def _setup(tmp_path, files):
    for f in files:
        (tmp_path / f).touch()


def _remaining(tmp_path):
    return {f.name for f in tmp_path.iterdir() if f.is_file()}


@pytest.mark.parametrize(
    "files_setup, expected_remaining",
    [
        # 1. Pure ISO alias: ger.srt redundant to de.ass
        pytest.param(
            ["v.de.ass", "v.ger.srt"],
            ["v.de.ass"],
            id="ger_alias_collapses_to_de",
        ),
        # 2. ISO-639-2 'deu' also resolves to 'de'
        pytest.param(
            ["v.de.ass", "v.deu.srt"],
            ["v.de.ass"],
            id="deu_alias_collapses_to_de",
        ),
        # 3. Full English name 'german' also resolves to 'de'
        pytest.param(
            ["v.de.ass", "v.german.srt"],
            ["v.de.ass"],
            id="german_alias_collapses_to_de",
        ),
        # 4. Same canonical lang, multiple inferior peers — all get trashed
        pytest.param(
            ["v.de.ass", "v.ger.srt", "v.deu.srt"],
            ["v.de.ass"],
            id="multiple_inferior_peers_all_trashed",
        ),
        # 5. Inferior alone (no preferred peer) — keep it
        pytest.param(
            ["v.ger.srt"],
            ["v.ger.srt"],
            id="lone_inferior_kept",
        ),
        # 6. Modifier protection: forced.srt is a different logical track
        #    than the main de.ass, so both must survive (Gemini-2026-05-09)
        pytest.param(
            ["v.de.ass", "v.de.forced.srt"],
            ["v.de.ass", "v.de.forced.srt"],
            id="forced_modifier_kept",
        ),
        pytest.param(
            ["v.de.ass", "v.de.sdh.srt"],
            ["v.de.ass", "v.de.sdh.srt"],
            id="sdh_modifier_kept",
        ),
        pytest.param(
            ["v.en.ass", "v.en.hi.srt"],
            ["v.en.ass", "v.en.hi.srt"],
            id="hi_modifier_kept",
        ),
        pytest.param(
            ["v.en.ass", "v.en.signs.srt"],
            ["v.en.ass", "v.en.signs.srt"],
            id="signs_modifier_kept",
        ),
        # 7. Same modifier across formats — should pair
        pytest.param(
            ["v.de.forced.ass", "v.de.forced.srt"],
            ["v.de.forced.ass"],
            id="same_modifier_pairs_correctly",
        ),
        # 8. Untagged sidecar (no language token at all) — never paired
        pytest.param(
            ["v.ass", "v.de.srt"],
            ["v.ass", "v.de.srt"],
            id="untagged_not_paired",
        ),
        # 9. Different videos in the same dir don't cross-pair
        pytest.param(
            ["a.de.ass", "b.ger.srt"],
            ["a.de.ass", "b.ger.srt"],
            id="different_videos_not_paired",
        ),
        # 10. Cross-language: en.srt + de.ass — independent tracks
        pytest.param(
            ["v.de.ass", "v.en.srt"],
            ["v.de.ass", "v.en.srt"],
            id="different_languages_kept",
        ),
        # 11. Akame real-case: de.ass + ger.srt + en.srt
        pytest.param(
            ["v.de.ass", "v.ger.srt", "v.en.srt"],
            ["v.de.ass", "v.en.srt"],
            id="akame_realcase_de_ger_en",
        ),
        # 12. Two preferred-format files for same canonical lang — both
        #     stay (out of scope — same-format dedup belongs in a
        #     separate rule per Gemini review).
        pytest.param(
            ["v.de.ass", "v.ger.ass"],
            ["v.de.ass", "v.ger.ass"],
            id="same_format_dedup_out_of_scope",
        ),
    ],
)
def test_format_upgrade_alias_aware(tmp_path, files_setup, expected_remaining, app_ctx):
    from services.cleanup_executors import execute_format_upgrade

    _setup(tmp_path, files_setup)
    config = {"keep_format": "ass", "permanent_delete": True}
    execute_format_upgrade(str(tmp_path), config, dry_run=False)

    assert _remaining(tmp_path) == set(expected_remaining)


def test_format_upgrade_dry_run_keeps_files(tmp_path, app_ctx):
    """dry_run must not touch the filesystem."""
    from services.cleanup_executors import execute_format_upgrade

    _setup(tmp_path, ["v.de.ass", "v.ger.srt"])
    result = execute_format_upgrade(
        str(tmp_path), {"keep_format": "ass"}, dry_run=True
    )

    assert result["would_delete"] == 1
    assert _remaining(tmp_path) == {"v.de.ass", "v.ger.srt"}


def test_format_upgrade_keep_srt_inverts_pairing(tmp_path, app_ctx):
    """keep_format='srt' should trash ASS when SRT exists."""
    from services.cleanup_executors import execute_format_upgrade

    _setup(tmp_path, ["v.de.ass", "v.ger.srt"])
    execute_format_upgrade(
        str(tmp_path), {"keep_format": "srt", "permanent_delete": True}, dry_run=False
    )

    # de.ass got trashed because ger.srt is the canonical-lang preferred-format peer
    assert _remaining(tmp_path) == {"v.ger.srt"}


def test_format_upgrade_any_is_noop(tmp_path, app_ctx):
    from services.cleanup_executors import execute_format_upgrade

    _setup(tmp_path, ["v.de.ass", "v.ger.srt"])
    result = execute_format_upgrade(str(tmp_path), {"keep_format": "any"}, dry_run=False)

    assert result == {"deleted": 0, "bytes_freed": 0}
    assert _remaining(tmp_path) == {"v.de.ass", "v.ger.srt"}


def test_classify_sidecar_handles_known_inputs(tmp_path):
    """Direct unit test of the classifier helper."""
    from services.cleanup_executors import _classify_sidecar

    # ger.srt → canonical 'de'
    p = tmp_path / "Show.S01E06.ger.srt"
    p.touch()
    res = _classify_sidecar(str(p))
    assert res is not None
    video_base, canonical_lang, modifier = res
    assert video_base == os.path.join(str(tmp_path), "Show.S01E06")
    assert canonical_lang == "de"
    assert modifier == ""

    # de.forced.ass → modifier preserved
    p2 = tmp_path / "Show.S01E06.de.forced.ass"
    p2.touch()
    res2 = _classify_sidecar(str(p2))
    assert res2 is not None
    assert res2[1] == "de"
    assert res2[2] == "forced"

    # untagged → None
    p3 = tmp_path / "Show.S01E06.ass"
    p3.touch()
    assert _classify_sidecar(str(p3)) is None

    # unrecognised lang token → None
    p4 = tmp_path / "Show.S01E06.xyzzy.srt"
    p4.touch()
    assert _classify_sidecar(str(p4)) is None

    # bare modifier without lang → None
    p5 = tmp_path / "Show.forced.srt"
    p5.touch()
    assert _classify_sidecar(str(p5)) is None
