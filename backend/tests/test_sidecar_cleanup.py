"""Tests for the non-target sidecar cleanup added in 0.51.11.

Covers:
  - normalize_language_code reverse lookup (ger→de, eng→en, jpn→ja,
    unknowns return lowercase/stripped)
  - _parse_sidecar_language handles plain, modifier, and non-sidecar names
  - trash_non_target_sidecars moves only non-keep languages and preserves
    unknown/undefined tags for safety
  - process_wanted_item short-circuits when the target language sidecar
    already exists on disk
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config_language_data import normalize_language_code
from remux import _parse_sidecar_language, trash_non_target_sidecars
from services.cleanup_executors import _detect_sidecar_language, execute_language_filter

# ---------------------------------------------------------------------------
# normalize_language_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("de", "de"),
        ("ger", "de"),
        ("deu", "de"),
        ("german", "de"),
        ("GER", "de"),  # case
        (" ger ", "de"),  # whitespace
        ("eng", "en"),
        ("jpn", "ja"),
        ("und", "und"),  # unknown stays unknown (not mapped)
        ("xx-yy", "xx-yy"),  # unknown stays lowercase/stripped
        ("", ""),  # empty
    ],
)
def test_normalize_language_code(raw, expected):
    assert normalize_language_code(raw) == expected


# ---------------------------------------------------------------------------
# _parse_sidecar_language
# ---------------------------------------------------------------------------


def test_parse_sidecar_lang_plain(tmp_path):
    base = tmp_path / "Show.S01E01"
    sidecar = f"{base}.en.ass"
    assert _parse_sidecar_language(sidecar, str(base)) == "en"


def test_parse_sidecar_lang_modifier_forced(tmp_path):
    base = tmp_path / "Show.S01E01"
    sidecar = f"{base}.en.forced.srt"
    assert _parse_sidecar_language(sidecar, str(base)) == "en"


def test_parse_sidecar_lang_modifier_sdh(tmp_path):
    base = tmp_path / "Movie"
    sidecar = f"{base}.de.sdh.ass"
    assert _parse_sidecar_language(sidecar, str(base)) == "de"


def test_parse_sidecar_lang_returns_none_for_unrelated_file(tmp_path):
    base = tmp_path / "Show.S01E01"
    sidecar = f"{tmp_path}/somethingElse.en.ass"
    assert _parse_sidecar_language(sidecar, str(base)) is None


def test_parse_sidecar_lang_returns_none_without_lang_segment(tmp_path):
    base = tmp_path / "Show.S01E01"
    sidecar = f"{base}.ass"  # no language token between base and ext
    assert _parse_sidecar_language(sidecar, str(base)) is None


def test_parse_sidecar_lang_rejects_unknown_ext(tmp_path):
    base = tmp_path / "Show.S01E01"
    sidecar = f"{base}.en.txt"
    assert _parse_sidecar_language(sidecar, str(base)) is None


# ---------------------------------------------------------------------------
# cleanup_executors._detect_sidecar_language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("Show.S01E01.en.hi.srt", "en"),
        ("Show.S01E01.ja.hi.srt", "ja"),
        ("Show.S01E01.en.forced.srt", "en"),
        ("Show.S01E01.en.srt", "en"),
        ("Movie.S01E01.ass", None),
        ("Show.S01E01.srt", None),
    ],
)
def test_detect_sidecar_language_handles_modifiers_without_reopening_c1_guard(
    tmp_path,
    filename,
    expected,
):
    assert _detect_sidecar_language(str(tmp_path / filename)) == expected


def test_a_bare_hi_suffix_is_left_unclassified_after_an_episode_marker(tmp_path):
    """``.hi`` is both a real ISO code (Hindi) and a modifier, and one token
    cannot be both. Where the name gives no language to attach the modifier to,
    the detector declines to classify — and an unclassified sidecar is KEPT.

    That is the safe direction on a path that trashes files: refusing to guess
    costs a Hindi user the ability to language-filter these, while guessing
    wrong deletes hearing-impaired subtitles, which is the failure this whole
    change exists to stop.

    ``Show.hi.srt`` still reads as Hindi: with no further token there is no
    modifier reading available, so the ambiguity does not arise.
    """
    assert _detect_sidecar_language(str(tmp_path / "Show.S01E01.hi.srt")) is None
    assert _detect_sidecar_language(str(tmp_path / "Show.hi.srt")) == "hi"


def test_language_filter_keeps_hearing_impaired_sidecar_when_language_is_kept(tmp_path):
    (tmp_path / "Show.S01E01.en.hi.srt").write_text("english hi sub")

    result = execute_language_filter(
        str(tmp_path),
        {"keep_languages": ["en"], "permanent_delete": True},
        dry_run=True,
    )

    assert result == {"would_delete": 0, "would_keep": 1, "examples": []}


def test_language_filter_can_delete_forced_sidecar_when_language_is_not_kept(tmp_path):
    sidecar = tmp_path / "Show.S01E01.en.forced.srt"
    sidecar.write_text("english forced sub")

    result = execute_language_filter(
        str(tmp_path),
        {"keep_languages": ["de"], "permanent_delete": True},
        dry_run=True,
    )

    assert result["would_delete"] == 1
    assert result["would_keep"] == 0
    assert result["examples"] == [
        {"path": str(sidecar), "size_bytes": sidecar.stat().st_size, "reason": "lang:en"}
    ]


# ---------------------------------------------------------------------------
# trash_non_target_sidecars
# ---------------------------------------------------------------------------


def _make_fixture(tmp_path: Path) -> Path:
    """Create a dummy video plus a handful of sidecars of varying languages."""
    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"fake-video")
    base = video.with_suffix("")
    for suffix in (".de.ass", ".en.ass", ".ger.ass", ".jpn.ass", ".fr.srt", ".und.ass"):
        (tmp_path / f"{base.name}{suffix}").write_text("dummy")
    return video


def test_trash_moves_only_non_target_languages(tmp_path):
    video = _make_fixture(tmp_path)

    moved = trash_non_target_sidecars(
        video_path=str(video),
        keep_langs={"de", "en"},
        trash_dir=str(tmp_path / "_trash"),
    )

    remaining = sorted(p.name for p in tmp_path.iterdir() if p.is_file())
    # de, en and und (unknown → kept for safety) survive; ger maps to de so it stays;
    # jpn and fr are trashed.
    assert "Show - S01E01.de.ass" in remaining
    assert "Show - S01E01.en.ass" in remaining
    assert "Show - S01E01.ger.ass" in remaining  # ger→de, kept
    assert "Show - S01E01.und.ass" in remaining  # undefined, preserved
    assert "Show - S01E01.jpn.ass" not in remaining
    assert "Show - S01E01.fr.srt" not in remaining

    moved_names = sorted(Path(src).name for src, _dst in moved)
    assert moved_names == ["Show - S01E01.fr.srt", "Show - S01E01.jpn.ass"]


def test_trash_is_noop_when_nothing_to_move(tmp_path):
    video = tmp_path / "Show.mkv"
    video.write_bytes(b"")
    (tmp_path / "Show.de.ass").write_text("x")
    (tmp_path / "Show.en.ass").write_text("x")

    moved = trash_non_target_sidecars(
        video_path=str(video),
        keep_langs={"de", "en"},
        trash_dir=str(tmp_path / "_trash"),
    )

    assert moved == []


def test_trash_collision_appends_timestamp(tmp_path):
    video = tmp_path / "Show.mkv"
    video.write_bytes(b"")
    (tmp_path / "Show.jpn.ass").write_text("x")

    trash_root = tmp_path / "_trash"
    # Pre-create a collision in today's trash subfolder.
    import datetime

    date_str = datetime.date.today().isoformat()
    existing_dir = trash_root / "trash" / date_str
    existing_dir.mkdir(parents=True)
    (existing_dir / "Show.jpn.ass").write_text("older")

    moved = trash_non_target_sidecars(
        video_path=str(video),
        keep_langs={"de"},
        trash_dir=str(trash_root),
    )
    assert len(moved) == 1
    # Destination must NOT overwrite the existing file — unique suffix added.
    _src, dst = moved[0]
    assert Path(dst).name != "Show.jpn.ass"
    assert Path(dst).exists()
    assert (existing_dir / "Show.jpn.ass").read_text() == "older"


# ---------------------------------------------------------------------------
# process_wanted_item — skip-when-satisfied
# ---------------------------------------------------------------------------


def test_process_wanted_item_skips_when_target_ass_exists(tmp_path):
    """When .{target}.ass exists next to the video, provider search is skipped."""
    from wanted_search.process import process_wanted_item

    video = tmp_path / "Show.mkv"
    video.write_bytes(b"")
    (tmp_path / "Show.de.ass").write_text("dummy subtitle")

    item = {
        "id": 42,
        "file_path": str(video),
        "target_language": "de",
        "search_count": 0,
    }
    settings = SimpleNamespace(
        target_language="de",
        source_language="en",
        upgrade_enabled=False,
        wanted_max_search_attempts=5,
        wanted_auto_translate=False,
    )

    provider_calls = []

    with (
        patch("wanted_search.process.get_wanted_item", return_value=item),
        patch("wanted_search.process.get_settings", return_value=settings),
        patch("wanted_search.process.update_existing_sub") as mock_update_sub,
        patch("wanted_search.process.update_wanted_status") as mock_update_status,
        patch(
            "wanted_search.process.get_provider_manager",
            side_effect=lambda: provider_calls.append("called") or None,
        ),
    ):
        result = process_wanted_item(42)

    assert result["status"] == "skipped"
    assert "already on disk" in result["reason"]
    assert "de" in result["reason"]
    # No provider manager was ever requested.
    assert provider_calls == []
    # Wanted item marked as extracted, not deleted (user may still want upgrade later)
    mock_update_sub.assert_called_once_with(42, "ass")
    mock_update_status.assert_called_once_with(42, "extracted")


def test_process_wanted_item_does_not_skip_when_srt_exists_and_upgrade_enabled(tmp_path):
    """SRT + upgrade_enabled must still fall through so the SRT→ASS upgrade can fire."""
    from wanted_search.process import process_wanted_item

    video = tmp_path / "Show.mkv"
    video.write_bytes(b"")
    (tmp_path / "Show.de.srt").write_text("dummy")

    item = {
        "id": 43,
        "file_path": str(video),
        "target_language": "de",
        "search_count": 0,
    }
    settings = SimpleNamespace(
        target_language="de",
        source_language="en",
        upgrade_enabled=True,
        wanted_max_search_attempts=5,
        wanted_auto_translate=False,
    )

    # The skip branch should NOT fire. We only test that the function does not
    # return `status=skipped` at the skip check point — the rest of process can
    # raise because we deliberately don't mock it.
    with (
        patch("wanted_search.process.get_wanted_item", return_value=item),
        patch("wanted_search.process.get_settings", return_value=settings),
        patch("wanted_search.process.update_wanted_status"),
        patch(
            "wanted_search.process.get_provider_manager",
            side_effect=RuntimeError("reached provider — skip did not fire, as expected"),
        ),
        pytest.raises(RuntimeError, match="skip did not fire"),
    ):
        process_wanted_item(43)


def test_process_wanted_item_skips_when_srt_exists_and_upgrade_disabled(tmp_path):
    """SRT + upgrade_enabled=False — the skip branch fires (target satisfied)."""
    from wanted_search.process import process_wanted_item

    video = tmp_path / "Show.mkv"
    video.write_bytes(b"")
    (tmp_path / "Show.de.srt").write_text("dummy")

    item = {
        "id": 44,
        "file_path": str(video),
        "target_language": "de",
        "search_count": 0,
    }
    settings = SimpleNamespace(
        target_language="de",
        source_language="en",
        upgrade_enabled=False,
        wanted_max_search_attempts=5,
        wanted_auto_translate=False,
    )

    with (
        patch("wanted_search.process.get_wanted_item", return_value=item),
        patch("wanted_search.process.get_settings", return_value=settings),
        patch("wanted_search.process.update_existing_sub") as mock_update_sub,
        patch("wanted_search.process.update_wanted_status") as mock_update_status,
        patch(
            "wanted_search.process.get_provider_manager",
            side_effect=RuntimeError("provider must not be touched"),
        ),
    ):
        result = process_wanted_item(44)

    assert result["status"] == "skipped"
    mock_update_sub.assert_called_once_with(44, "srt")
    mock_update_status.assert_called_once_with(44, "extracted")
