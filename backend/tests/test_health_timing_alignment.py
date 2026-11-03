"""Health sweep: sidecars already on disk whose timing does not fit the video.

Prod 2026-11 (Mushoku Tensei S01): English sidecars 6 s late (E20) or for
another cut (E17, E21) sat next to the videos for months.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import subtitle_timing
from services.subtitle_health.checkers import timing_alignment
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target
from subtitle_dialogue import dialogue_starts
from subtitle_timing import Reference
from tests.test_subtitle_timing import _speech, _srt, _translation_of


def _ctx(tmp_path, *targets):
    video = tmp_path / "Show - S01E20.mp4"
    video.write_bytes(b"")
    return ScanContext(episode_id=20, video_path=str(video), targets=list(targets))


def _sidecar(tmp_path, suffix: str, content: bytes, *, forced=False) -> Target:
    path = tmp_path / f"Show - S01E20{suffix}"
    path.write_bytes(content)
    return Target(
        kind=TargetKind.SIDECAR,
        path=str(path),
        stream_index=None,
        lang=suffix.split(".")[1],
        codec="subrip",
        raw=content,
        forced=forced,
    )


def _detect(ctx, reference, overruns=False):
    with (
        patch.object(subtitle_timing, "find_reference", return_value=reference),
        patch.object(timing_alignment, "_overruns", return_value=overruns),
    ):
        return timing_alignment.detect(ctx)


SPEECH = _speech()


class TestDetect:
    def test_a_late_track_against_an_embedded_reference_is_shifted(self, tmp_path):
        late = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(SPEECH, offset=6.0)))
        [issue] = _detect(_ctx(tmp_path, late), Reference(SPEECH, True, "embedded"))
        assert issue.type == IssueType.TIMING_OFFSET
        assert issue.severity == Severity.CONFIRMED
        assert issue.suggested_fix == timing_alignment.SHIFT_ACTION

    def test_another_cut_against_an_embedded_reference_is_quarantined(self, tmp_path):
        wrong = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(_speech(seed=9))))
        [issue] = _detect(_ctx(tmp_path, wrong), Reference(SPEECH, True, "embedded"))
        assert issue.type == IssueType.TIMING_MISMATCH
        assert issue.suggested_fix == timing_alignment.QUARANTINE_ACTION

    def test_against_another_sidecar_a_mismatch_is_only_suspicious(self, tmp_path):
        # Which of the two is wrong cannot be told from their timing alone.
        wrong = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(_speech(seed=9))))
        [issue] = _detect(_ctx(tmp_path, wrong), Reference(SPEECH, False, "sidecar de"))
        assert issue.severity == Severity.SUSPICIOUS
        assert issue.suggested_fix is None

    def test_a_mismatch_that_runs_past_the_video_is_the_wrong_one(self, tmp_path):
        # E21: the English track ended 81 s after the episode.
        wrong = _sidecar(tmp_path, ".en.ass", _srt(_translation_of(_speech(seed=9))))
        [issue] = _detect(
            _ctx(tmp_path, wrong), Reference(SPEECH, False, "sidecar de"), overruns=True
        )
        assert issue.severity == Severity.CONFIRMED
        assert issue.suggested_fix == timing_alignment.QUARANTINE_ACTION

    def test_a_shift_against_another_sidecar_is_not_applied(self, tmp_path):
        late = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(SPEECH, offset=6.0)))
        [issue] = _detect(_ctx(tmp_path, late), Reference(SPEECH, False, "sidecar de"))
        assert issue.suggested_fix is None

    @pytest.mark.parametrize("suffix", [".en.srt"])
    def test_fitting_and_forced_tracks_raise_nothing(self, tmp_path, suffix):
        fits = _sidecar(tmp_path, suffix, _srt(_translation_of(SPEECH)))
        forced = _sidecar(
            tmp_path, ".en.forced.srt", _srt(_translation_of(_speech(seed=9))), forced=True
        )
        assert _detect(_ctx(tmp_path, fits, forced), Reference(SPEECH, True, "embedded")) == []

    def test_no_reference_raises_nothing(self, tmp_path):
        wrong = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(_speech(seed=9))))
        assert _detect(_ctx(tmp_path, wrong), None) == []


def test_shift_fixer_remeasures_and_keeps_a_backup(tmp_path):
    from services.subtitle_health.fixers import shift_timing

    late = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(SPEECH, offset=6.0)))
    with (
        patch.object(subtitle_timing, "find_reference", return_value=Reference(SPEECH, True, "e")),
        patch(
            "services.subtitle_health.fixers.shift_timing.backup_sidecar", return_value="/t/bak"
        ) as backup,
        patch("services.subtitle_health.store.record_fix", return_value=7),
    ):
        result = shift_timing.apply_to_sidecar(late.path, "/media/v.mp4", finding_id=1)

    assert result["changed"] and result["fix_id"] == 7
    assert result["shifted_s"] == pytest.approx(-6.0, abs=0.2)
    backup.assert_called_once_with(late.path)
    with open(late.path, "rb") as fh:
        fixed = dialogue_starts(fh.read())
    assert subtitle_timing.align(SPEECH, fixed).verdict == subtitle_timing.FIT


def test_shift_fixer_refuses_an_untrusted_reference(tmp_path):
    from services.subtitle_health.fixers import shift_timing

    late = _sidecar(tmp_path, ".en.srt", _srt(_translation_of(SPEECH, offset=6.0)))
    with patch.object(
        subtitle_timing, "find_reference", return_value=Reference(SPEECH, False, "sidecar")
    ):
        result = shift_timing.apply_to_sidecar(late.path, "/media/v.mp4")
    assert not result["changed"]


def test_sweep_repairs_confirmed_timing_findings_with_auto_fix_off(tmp_path):
    from services.subtitle_health import sweep

    findings = [
        {"id": 1, "suggested_fix": "shift_timing", "target_kind": "sidecar", "target_path": "a"},
        {"id": 2, "suggested_fix": None, "target_kind": "sidecar", "target_path": "b"},
        {
            "id": 3,
            "suggested_fix": "quarantine_wrong_sidecar",
            "target_kind": "sidecar",
            "target_path": "c",
        },
    ]
    with (
        patch.object(sweep, "_is_stable", return_value=True),
        patch.object(sweep, "is_suspect_sidecar", return_value=False),
        patch.object(sweep, "apply_fix", return_value={"changed": True}) as apply_fix,
    ):
        sweep._repair_timing(findings, "/media/v.mp4")

    assert [c.args for c in apply_fix.call_args_list] == [
        (1, "shift_timing"),
        (3, "quarantine_wrong_sidecar"),
    ]
