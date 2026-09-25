"""An upgrade may only replace a real subtitle with a better real one.

Two defects met on prod 2026-09-24, both on items that already carry a genuine
target-language SRT (an upgrade candidate):

* The upgrade logic knew only the canonical ``.de.srt``. A sidecar written
  under a raw container code (``.ger.srt``, ``.eng.srt``) was neither scored
  nor retired, so the item was searched as plainly "wanted" and any hit landed
  as a second German subtitle next to it (320 rows in that state, 178 more
  about to join them).
* After Step 1 (target ASS) found nothing, the item ran on into the source
  translation steps and the unscored SRT step. 116 files got a machine
  translation after a real subtitle of the same language was already there —
  against the owner's rule that a self-made translation is always the last
  resort (decision 2026-09-13).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from providers.base import SubtitleFormat

# --- the helper: which target sidecar is actually on disk -------------------


def _touch(path, text="1\n00:00:01,000 --> 00:00:02,000\nHallo\n"):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_finds_the_canonical_sidecar_first(tmp_path):
    from translator.output_paths import find_existing_target_file

    video = tmp_path / "Show - S01E01.mkv"
    canonical = _touch(tmp_path / "Show - S01E01.de.srt")
    _touch(tmp_path / "Show - S01E01.ger.srt")
    assert find_existing_target_file(str(video), "de", "srt") == canonical


def test_finds_a_raw_code_sidecar(tmp_path):
    from translator.output_paths import find_existing_target_file

    video = tmp_path / "Show - S01E01.mkv"
    alias = _touch(tmp_path / "Show - S01E01.ger.srt")
    assert find_existing_target_file(str(video), "de", "srt") == alias


def test_finds_nothing_when_nothing_is_there(tmp_path):
    from translator.output_paths import find_existing_target_file

    video = tmp_path / "Show - S01E01.mkv"
    _touch(tmp_path / "Show - S01E01.en.srt")
    assert find_existing_target_file(str(video), "de", "srt") is None


# --- the scanner scores the file that is really there -----------------------


def test_scanner_scores_a_raw_code_sidecar(tmp_path):
    from services.wanted_item_scanner import _check_language_for_item

    video = tmp_path / "Show - S01E01.mkv"
    alias = _touch(tmp_path / "Show - S01E01.ger.srt")
    scored = []

    def score(path):
        scored.append(path)
        return "srt", 61

    settings = MagicMock(upgrade_enabled=True)
    with patch("services.wanted_item_scanner.score_existing_subtitle", side_effect=score):
        result = _check_language_for_item(str(video), "de", None, settings)

    assert result is not None
    assert result["existing_sub"] == "srt"
    assert result["upgrade_candidate"] is True
    assert result["current_score"] == 61
    assert scored == [alias]


# --- Step 1 judges and retires the file that is really there ---------------


def _ctx(video, *, upgrade=True, score=40):
    result = SimpleNamespace(
        content=b"[Script Info]\n",
        score=300,
        provider_name="animetosho",
        subtitle_id="x1",
        format=SubtitleFormat.ASS,
        score_breakdown={},
        language="de",
    )
    manager = MagicMock()
    manager.search_and_download_best.return_value = result

    def save(res, output_path, series_id=None):
        with open(output_path, "wb") as fh:
            fh.write(res.content)
        return output_path

    manager.save_subtitle.side_effect = save
    settings = MagicMock(
        upgrade_prefer_ass=True,
        upgrade_min_score_delta=0,
        upgrade_window_days=0,
        upgrade_protect_user_modified=True,
    )
    return {
        "item": {"id": 7, "sonarr_series_id": None},
        "item_id": 7,
        "item_lang": "de",
        "settings": settings,
        "manager": manager,
        "query": MagicMock(),
        "_pf": {"must_contain": [], "must_not_contain": []},
        "file_path": str(video),
        "is_upgrade": upgrade,
        "current_score": score,
        "dry_run": False,
    }


@pytest.fixture
def _step1_side_effects():
    from wanted_search import process as proc

    with (
        patch.object(proc, "should_upgrade", return_value=(True, "ass beats srt")) as judge,
        patch.object(proc, "record_upgrade"),
        patch.object(proc, "record_subtitle_download"),
        patch.object(proc, "delete_wanted_item"),
        patch.object(proc, "update_wanted_status"),
        patch.object(proc, "verify_dubtitle_on_keep", return_value=True),
        patch.object(proc, "_try_auto_sync"),
        patch("nfo_export.maybe_write_nfo"),
        patch("services.subtitle_restore.backup_before_replace") as backup,
        patch("db.quality.is_user_modified", return_value=False) as guard,
        patch("db.quality.clear_user_modified"),
        patch("db.providers.get_latest_download_id", return_value=None),
    ):
        yield SimpleNamespace(judge=judge, backup=backup, guard=guard)


def test_upgrade_retires_the_raw_code_sidecar_it_replaces(tmp_path, _step1_side_effects):
    """One German subtitle before, one after — the .ger.srt must not survive."""
    from wanted_search import process as proc

    video = tmp_path / "Show - S01E01.mkv"
    alias = _touch(tmp_path / "Show - S01E01.ger.srt")

    result = proc._try_target_ass_direct(_ctx(video))

    assert result["status"] == "found"
    assert (tmp_path / "Show - S01E01.de.ass").exists()
    assert not (tmp_path / "Show - S01E01.ger.srt").exists(), "second German subtitle left behind"
    _step1_side_effects.backup.assert_called_once_with(alias)
    _step1_side_effects.guard.assert_called_once_with(alias)
    assert _step1_side_effects.judge.call_args.kwargs["existing_file_path"] == alias


def test_upgrade_still_retires_a_canonical_sidecar(tmp_path, _step1_side_effects):
    from wanted_search import process as proc

    video = tmp_path / "Show - S01E01.mkv"
    canonical = _touch(tmp_path / "Show - S01E01.de.srt")

    result = proc._try_target_ass_direct(_ctx(video))

    assert result["status"] == "found"
    assert not (tmp_path / "Show - S01E01.de.srt").exists()
    _step1_side_effects.backup.assert_called_once_with(canonical)


# --- an upgrade candidate never reaches translation or the unscored SRT step


@pytest.fixture
def _steps():
    from wanted_search import process as proc

    with (
        patch.object(proc, "_try_target_ass_direct", return_value=None) as s1,
        patch.object(proc, "_try_source_ass_translation") as s2,
        patch.object(proc, "_try_target_srt_direct") as s3,
        patch.object(proc, "_try_source_srt_translation") as s4,
        patch.object(proc, "_fallback_translate_file") as s5,
        patch.object(proc, "update_wanted_status") as status,
        patch("services.wanted_search_runner.record_search_outcome") as outcome,
        patch("services.series_format.get_series_format_requirement", return_value=None),
    ):
        yield SimpleNamespace(s1=s1, s2=s2, s3=s3, s4=s4, s5=s5, status=status, outcome=outcome)


def _orchestrator_ctx(*, is_upgrade):
    settings = MagicMock(wanted_skip_srt_on_no_ass=False)
    return {
        "item": {"id": 42, "sonarr_series_id": None},
        "item_id": 42,
        "settings": settings,
        "auto_translate": True,
        "ass_had_results": False,
        "dry_run": False,
        "allow_translate_fallback": True,
        "is_upgrade": is_upgrade,
    }


def test_upgrade_candidate_stops_after_step_one(_steps):
    from wanted_search import process as proc

    result = proc._run_search_steps(_orchestrator_ctx(is_upgrade=True))

    _steps.s1.assert_called_once()
    for name, step in (("2", _steps.s2), ("3", _steps.s3), ("4", _steps.s4), ("5", _steps.s5)):
        assert not step.called, f"Step {name} ran for an item that already has a real subtitle"
    assert result["status"] == "not_found"
    _steps.status.assert_called_with(42, "wanted")
    _steps.outcome.assert_called_once_with(42, kind="no_result")


def test_a_plain_wanted_item_still_runs_every_step(_steps):
    """The guard is for upgrades only — a missing subtitle keeps every fallback."""
    from wanted_search import process as proc

    for step in (_steps.s2, _steps.s3, _steps.s4):
        step.return_value = None
    _steps.s5.return_value = {"wanted_id": 42, "status": "not_found"}

    proc._run_search_steps(_orchestrator_ctx(is_upgrade=False))

    for step in (_steps.s2, _steps.s3, _steps.s4, _steps.s5):
        step.assert_called_once()


# --- scanner, end to end on real files (detection is NOT mocked) ------------
#
# detect_existing_target_for_lang also answers "srt" for an EMBEDDED SRT when
# given probe data. A first cut of the scanner fix read "existing == srt" as
# "a sidecar is on disk" and, with mocked detection in its tests, never saw
# that episodes carrying only an embedded SRT stopped being extracted.

_EMBEDDED_GER_SRT = {
    "streams": [
        {"codec_type": "audio", "codec_name": "aac", "tags": {"language": "jpn"}},
        {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "ger"}},
    ]
}


def _scan_real(tmp_path, *sidecars):
    from services.wanted_item_scanner import _check_language_for_item

    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"")
    for name in sidecars:
        _touch(tmp_path / f"Show - S01E01.{name}")
    return _check_language_for_item(
        str(video), "de", _EMBEDDED_GER_SRT, MagicMock(upgrade_enabled=True)
    )


def test_real_embedded_srt_without_sidecar_is_still_extracted(tmp_path):
    result = _scan_real(tmp_path)
    assert result["existing_sub"] == "embedded_srt"
    assert result["upgrade_candidate"] is False


def test_real_sidecar_plus_embedded_srt_is_an_upgrade_candidate(tmp_path):
    result = _scan_real(tmp_path, "de.srt")
    assert result["existing_sub"] == "srt"
    assert result["upgrade_candidate"] is True


def test_real_alias_sidecar_plus_embedded_srt_is_an_upgrade_candidate(tmp_path):
    result = _scan_real(tmp_path, "ger.srt")
    assert result["existing_sub"] == "srt"
    assert result["upgrade_candidate"] is True


def test_real_embedded_target_ass_satisfies_the_language(tmp_path):
    """Unchanged behaviour, pinned: an embedded target ASS is as good as done.

    Detection answers "ass" for the track itself, so no wanted row is kept —
    whatever SRT sidecar lies beside it.
    """
    from services.wanted_item_scanner import _check_language_for_item

    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"")
    _touch(tmp_path / "Show - S01E01.de.srt")
    probe = {
        "streams": [
            {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "ger"}},
        ]
    }
    assert (
        _check_language_for_item(str(video), "de", probe, MagicMock(upgrade_enabled=True)) is None
    )
