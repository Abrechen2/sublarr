"""A full sidecar that is really signs/credits only counts as missing.

Prod 2026-11: a German ``.de.ass`` with exactly 10 Dialogue lines (a title card
and the credits, no dialogue) for a 24-minute episode counted as the full
subtitle, so the episode was never searched again.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import subtitle_plausibility
from services import suspect_sidecars
from subtitle_dialogue import assess_content, sparse_sidecar_reason

pytestmark = pytest.mark.usefixtures("auto_repair_on")

EPISODE_S = 1422.0

_HEAD = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20
Style: Credits,Arial,20
Style: TypePlaceholder,Arial,20

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _line(style: str, start: float, text: str) -> str:
    return f"Dialogue: 0,{_ts(start)},{_ts(start + 3)},{style},,0,0,0,,{text}"


def credits_only_ass() -> bytes:
    """The prod file: 1 title card, 5 credits, 4 placeholders = 10 lines."""
    lines = [_line("Default", 0.0, "Title Card")]
    lines += [_line("Credits", 1320.0 + i * 4, f"Credit {i}") for i in range(5)]
    lines += [_line("TypePlaceholder", 1410.0 + i * 3, f"Placeholder {i}") for i in range(4)]
    return (_HEAD + "\n".join(lines) + "\n").encode()


def full_ass(n: int = 300) -> bytes:
    step = 1400.0 / n
    lines = [_line("Default", i * step, f"Dialogue line {i}") for i in range(n)]
    return (_HEAD + "\n".join(lines) + "\n").encode()


def full_srt(n: int = 120) -> bytes:
    blocks = [
        f"{i}\n00:{i // 60:02d}:{i % 60:02d},000 --> 00:{i // 60:02d}:{i % 60:02d},900\nLine {i}\n"
        for i in range(1, n)
    ]
    return "\n".join(blocks).encode()


@pytest.fixture
def video(tmp_path, monkeypatch):
    path = tmp_path / "Show.S01E01.mkv"
    path.write_bytes(b"x")
    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: EPISODE_S)
    return str(path)


def _write(video: str, suffix: str, content: bytes) -> str:
    path = os.path.splitext(video)[0] + suffix
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def test_fixture_is_ten_lines_and_sparse():
    assessment = assess_content(credits_only_ass(), EPISODE_S)
    assert assessment is not None
    assert assessment.sparse_reason


def test_credits_only_sidecar_is_sparse_and_full_one_is_not(video):
    sparse = _write(video, ".de.ass", credits_only_ass())
    assert sparse_sidecar_reason(sparse, video)
    full = _write(video, ".en.ass", full_ass())
    assert sparse_sidecar_reason(full, video) is None


def test_unknown_duration_never_flags(video, monkeypatch):
    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: None)
    sparse = _write(video, ".de.ass", credits_only_ass())
    assert sparse_sidecar_reason(sparse, video) is None
    assert suspect_sidecars.existing_ignoring_suspects(video, "de", "ass") == "ass"


def test_sparse_ass_counts_as_missing_and_stays_on_disk(video):
    path = _write(video, ".de.ass", credits_only_ass())
    assert suspect_sidecars.existing_ignoring_suspects(video, "de", "ass") is None
    assert os.path.exists(path)


def test_without_automatic_repair_a_sparse_ass_still_counts(video):
    _write(video, ".de.ass", credits_only_ass())
    with patch("services.auto_repair.auto_repair_enabled", return_value=False):
        assert suspect_sidecars.existing_ignoring_suspects(video, "de", "ass") == "ass"
        assert suspect_sidecars.sparse_full_sidecar(video, "de") is None


def test_sparse_ass_next_to_genuine_srt_reads_srt(video):
    _write(video, ".de.ass", credits_only_ass())
    _write(video, ".de.srt", full_srt())
    assert suspect_sidecars.existing_ignoring_suspects(video, "de", "ass") == "srt"


def test_real_full_sub_is_kept(video):
    _write(video, ".de.ass", full_ass())
    assert suspect_sidecars.existing_ignoring_suspects(video, "de", "ass") == "ass"


@pytest.mark.parametrize("suffix", [".de.forced.ass", ".de.signs.ass", ".de.signs-songs.ass"])
def test_forced_and_signs_sidecars_are_untouched(video, suffix):
    path = _write(video, suffix, credits_only_ass())
    assert suspect_sidecars.sparse_full_sidecar(video, "de") is None
    # With a genuine full sidecar next to it nothing changes either.
    _write(video, ".de.ass", full_ass())
    assert suspect_sidecars.existing_ignoring_suspects(video, "de", "ass") == "ass"
    assert os.path.exists(path)


# --- the three call sites ---------------------------------------------------------


def test_sonarr_radarr_scanner_wants_the_episode(video):
    from services.wanted_item_scanner import _check_language_for_item

    _write(video, ".de.ass", credits_only_ass())
    result = _check_language_for_item(video, "de", None, SimpleNamespace(upgrade_enabled=False))
    assert result is not None
    assert result["existing_sub"] == ""


def test_sonarr_radarr_scanner_keeps_a_full_sub_satisfied(video):
    from services.wanted_item_scanner import _check_language_for_item

    _write(video, ".de.ass", full_ass())
    settings = SimpleNamespace(upgrade_enabled=False)
    assert _check_language_for_item(video, "de", None, settings) is None


def test_standalone_scanner_does_not_count_sparse(video):
    from standalone.scanner import StandaloneScanner

    _write(video, ".de.ass", credits_only_ass())
    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        assert StandaloneScanner._check_existing_subtitle(MagicMock(), video, "de") is None
    _write(video, ".de.ass", full_ass())
    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        assert StandaloneScanner._check_existing_subtitle(MagicMock(), video, "de") == "ass"


def test_search_does_not_skip_on_sparse_sidecar(video):
    from wanted_search.process import _check_existing_sidecar

    settings = SimpleNamespace(upgrade_enabled=False)
    item = {"file_path": video, "subtitle_type": "full"}
    _write(video, ".de.ass", credits_only_ass())
    with (
        patch("wanted_search.process.update_existing_sub"),
        patch("wanted_search.process.update_wanted_status"),
    ):
        assert _check_existing_sidecar(item, 1, "de", settings) is None
        _write(video, ".de.ass", full_ass())
        skipped = _check_existing_sidecar(item, 1, "de", settings)
    assert skipped is not None and skipped["status"] == "skipped"


def test_translation_fallback_does_not_stop_at_a_sparse_sidecar(video):
    """Prod 2026-11-12: a 4-line ".de.srt" (title, credits, preview) kept the
    episode wanted, yet the queued translation stopped at "a real target
    subtitle exists" — every tick, for good."""
    from wanted_search.process import _target_subtitle_on_disk

    ctx = {"file_path": video, "item_lang": "de"}
    sparse = _write(video, ".de.ass", credits_only_ass())
    assert _target_subtitle_on_disk(ctx) is None
    with patch("services.auto_repair.auto_repair_enabled", return_value=False):
        assert _target_subtitle_on_disk(ctx) == sparse
    full = _write(video, ".de.srt", full_srt())
    assert _target_subtitle_on_disk(ctx) == full


def test_search_leaves_a_forced_item_alone(video):
    from wanted_search.process import _check_existing_sidecar

    _write(video, ".de.forced.ass", credits_only_ass())
    item = {"file_path": video, "subtitle_type": "forced"}
    with (
        patch("wanted_search.process.update_existing_sub"),
        patch("wanted_search.process.update_wanted_status"),
    ):
        result = _check_existing_sidecar(item, 1, "de", SimpleNamespace(upgrade_enabled=False))
    assert result is not None  # the forced file satisfies the forced item


# --- requeue --------------------------------------------------------------------


def _exhausted_row(video: str) -> int:
    from datetime import UTC, datetime

    from db.models.core import WantedItem
    from extensions import db

    now = datetime.now(UTC)
    item = WantedItem(
        added_at=now,
        updated_at=now,
        item_type="episode",
        file_path=video,
        title="T",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        search_count=9,
        failure_kind="no_result_slow",
    )
    db.session.add(item)
    db.session.commit()
    return item.id


def test_scan_note_gives_back_attempts_once(app_ctx, video):
    from db.models.core import WantedItem
    from extensions import db

    _write(video, ".de.ass", credits_only_ass())
    item_id = _exhausted_row(video)
    suspect_sidecars.note_sparse_sidecar(video, "de")
    db.session.expire_all()
    assert db.session.get(WantedItem, item_id).search_count == 0
    # Slow mode again after a failed search: the same file version is not noted twice.
    row = db.session.get(WantedItem, item_id)
    row.search_count = 9
    db.session.commit()
    suspect_sidecars.note_sparse_sidecar(video, "de")
    db.session.expire_all()
    assert db.session.get(WantedItem, item_id).search_count == 9


def test_requeue_clears_backoff(app_ctx, video):
    from db.models.core import WantedItem
    from extensions import db

    _write(video, ".de.ass", credits_only_ass())
    item_id = _exhausted_row(video)
    with patch.object(suspect_sidecars, "_arr_lists", return_value=([], [])):
        assert suspect_sidecars.requeue_sparse_sidecar(video, "de") is True
        assert suspect_sidecars.requeue_sparse_sidecar(video, "de") is False
    db.session.expire_all()
    assert db.session.get(WantedItem, item_id).search_count == 0


def test_requeue_skips_a_full_sidecar(app_ctx, video):
    _write(video, ".de.ass", full_ass())
    assert suspect_sidecars.requeue_sparse_sidecar(video, "de") is False


# --- subtitle health ---------------------------------------------------------------


def _ctx(raw, video="/m/x.mkv", forced=False):
    from services.subtitle_health.models import TargetKind
    from services.subtitle_health.scan import ScanContext, Target

    return ScanContext(
        episode_id=1,
        video_path=video,
        targets=[
            Target(
                kind=TargetKind.SIDECAR,
                path="/m/x.de.ass",
                stream_index=None,
                lang="de",
                codec="ass",
                raw=raw,
                forced=forced,
            )
        ],
    )


def test_health_checker_flags_exactly_ten_lines(video):
    from services.subtitle_health.checkers.empty_or_tiny import REQUEUE_ACTION, detect
    from services.subtitle_health.models import Severity

    issues = detect(_ctx(credits_only_ass(), video))
    assert len(issues) == 1
    assert issues[0].severity == Severity.SUSPICIOUS
    assert issues[0].count == 10
    assert issues[0].suggested_fix == REQUEUE_ACTION  # never trash: the file is kept


def test_health_checker_passes_a_full_sub_and_forced(video):
    from services.subtitle_health.checkers.empty_or_tiny import detect

    assert detect(_ctx(full_ass(), video)) == []
    assert detect(_ctx(credits_only_ass(), video, forced=True)) == []


def test_health_checker_unknown_duration_keeps_ten_lines(video, monkeypatch):
    from services.subtitle_health.checkers.empty_or_tiny import detect

    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: None)
    assert detect(_ctx(credits_only_ass(), video)) == []


def test_sweep_requeues_a_sparse_finding(app_ctx):
    from services.subtitle_health import sweep

    findings = [
        {"suggested_fix": "requeue_search", "target_kind": "sidecar", "lang": "de"},
        {"suggested_fix": "trash_sidecar", "target_kind": "sidecar", "lang": "de"},
    ]
    with (
        patch("services.subtitle_health.sweep.scan_episode"),
        patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
        patch("services.subtitle_health.sweep.episode_sidecars", return_value=[]),
        patch(
            "services.subtitle_health.sweep.store.get_findings_for_episode", return_value=findings
        ),
        patch("services.suspect_sidecars.requeue_sparse_sidecar") as requeue,
    ):
        assert sweep._sweep_episode(5, "/m/e.mkv", False) is True
        requeue.assert_called_once_with("/m/e.mkv", "de")
        requeue.reset_mock()
        with patch("services.auto_repair.auto_repair_enabled", return_value=False):
            assert sweep._sweep_episode(5, "/m/e.mkv", False) is True
        requeue.assert_not_called()


def test_a_full_srt_retires_the_sparse_ass_it_replaces(video):
    sparse = _write(video, ".de.ass", credits_only_ass())
    saved = _write(video, ".de.srt", full_srt(300))
    with patch.object(suspect_sidecars, "_trash", side_effect=lambda paths: list(paths)) as trash:
        suspect_sidecars.retire_sparse_siblings(saved, "de")
    trash.assert_called_once_with([sparse])


def test_a_sparse_save_or_a_forced_save_retires_nothing(video):
    _write(video, ".de.ass", credits_only_ass())
    sparse_srt = _write(video, ".de.srt", credits_only_ass())
    forced = _write(video, ".de.forced.srt", full_srt(300))
    with patch.object(suspect_sidecars, "_trash", side_effect=lambda paths: list(paths)) as trash:
        suspect_sidecars.retire_sparse_siblings(sparse_srt, "de")
        suspect_sidecars.retire_sparse_siblings(forced, "de")
    assert all(call.args == ([],) for call in trash.call_args_list)


def test_a_full_sibling_is_never_retired(video):
    _write(video, ".de.ass", full_ass())
    saved = _write(video, ".de.srt", full_srt(300))
    with patch.object(suspect_sidecars, "_trash", side_effect=lambda paths: list(paths)) as trash:
        suspect_sidecars.retire_sparse_siblings(saved, "de")
    trash.assert_called_once_with([])
