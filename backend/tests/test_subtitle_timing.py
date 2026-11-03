"""Timing check: a subtitle's lines must start when the video's lines start.

Prod 2026-11 (Mushoku Tensei S01): an English sidecar 6 s late, and two that
matched no line of their episode, sat next to the video for months.
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock, patch

import pytest

import subtitle_timing
from providers.base import SubtitleResult, VideoQuery
from subtitle_dialogue import dialogue_starts
from subtitle_timing import FIT, MISMATCH, SHIFT, UNCERTAIN, Reference, align, shift_content

DURATION = 1422.0


def _speech(n: int = 320, seed: int = 1) -> list[float]:
    """Line starts of a 24-minute episode: irregular gaps of 1-8 s."""
    rng = random.Random(seed)
    t, out = 5.0, []
    while len(out) < n and t < DURATION - 5:
        out.append(round(t, 2))
        t += rng.uniform(1.0, 8.0)
    return out


def _translation_of(starts: list[float], seed: int = 2, offset: float = 0.0) -> list[float]:
    """The same speech subtitled again: jitter, some lines merged or split."""
    rng = random.Random(seed)
    out = []
    for t in starts:
        roll = rng.random()
        if roll < 0.08:
            continue  # merged into the previous line
        out.append(round(t + offset + rng.uniform(-0.15, 0.15), 2))
        if roll > 0.94:
            out.append(round(t + offset + 1.5, 2))  # split in two
    return sorted(out)


def _srt(starts: list[float]) -> bytes:
    def ts(s: float) -> str:
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    blocks = [f"{i}\n{ts(t)} --> {ts(t + 1.2)}\nLine {i}\n" for i, t in enumerate(starts, 1)]
    return "\n".join(blocks).encode()


class TestAlign:
    def test_the_same_speech_in_another_language_fits(self):
        speech = _speech()
        alignment = align(speech, _translation_of(speech))
        assert alignment.verdict == FIT
        assert alignment.match >= 0.8
        assert abs(alignment.offset_s) <= 0.2

    def test_a_constant_delay_is_found_to_be_undone(self):
        speech = _speech()
        alignment = align(speech, _translation_of(speech, offset=6.3))
        assert alignment.verdict == SHIFT
        assert alignment.offset_s == pytest.approx(6.3, abs=0.2)

    def test_an_early_track_is_found_too(self):
        speech = _speech()
        alignment = align(speech, _translation_of(speech, offset=-41.0))
        assert alignment.verdict == SHIFT
        assert alignment.offset_s == pytest.approx(-41.0, abs=0.2)

    def test_another_episode_is_a_mismatch(self):
        # Prod: the S01E23 track against S01E22 found 19 % at its best offset.
        alignment = align(_speech(seed=22), _translation_of(_speech(seed=23)))
        assert alignment.verdict == MISMATCH
        assert alignment.match < 0.35

    def test_a_different_cut_is_a_mismatch(self):
        # A recap inserted at minute 3 moves everything after it by a different
        # amount than before: no single offset fits most lines.
        speech = _speech()
        recut = [t if t < 180 else t + 37.0 for t in _translation_of(speech)]
        recut = [t * 1.04 for t in recut]  # and a frame-rate mismatch on top
        assert align(speech, recut).verdict == MISMATCH

    def test_a_partly_matching_track_is_uncertain_not_rejected(self):
        speech = _speech()
        half = _translation_of(speech[: len(speech) // 2]) + [
            t + 23.0 for t in speech[len(speech) // 2 :]
        ]
        assert align(speech, sorted(half)).verdict == UNCERTAIN

    def test_hostile_line_counts_give_no_verdict(self):
        # Provider content: 6,000+ lines, or thousands piled into one minute,
        # must not turn the check into minutes of work.
        assert align(_speech(), [5.0 + i / 1000 for i in range(7000)]) is None
        crowded = sorted([60.0 + i / 100 for i in range(5000)])
        assert align(crowded, crowded) is None

    def test_too_few_lines_give_no_verdict(self):
        assert align(_speech(30), _speech(30)) is None
        assert align(_speech(), _speech(12)) is None


def test_dialogue_starts_leave_signs_out():
    ass = (
        b"[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        b"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        b"BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        b"BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        b"Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        b"100,100,0,0,1,2,0,2,10,10,10,1\n"
        b"Style: Signs,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        b"100,100,0,0,1,2,0,8,10,10,10,1\n\n[Events]\n"
        b"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        b"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello\n"
        b"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello\n"
        b"Dialogue: 0,0:00:03.50,0:00:04.00,Signs,,0,0,0,,{\\pos(10,10)}SHOP\n"
        b"Dialogue: 0,0:00:05.25,0:00:06.00,Default,Sign,0,0,0,,EXIT\n"
        b"Dialogue: 0,0:00:07.00,0:00:08.00,Default,,0,0,0,,Bye\n"
    )
    assert dialogue_starts(ass) == [1.0, 7.0]


def test_shift_moves_every_line_and_keeps_the_format():
    shifted = shift_content(_srt([10.0, 20.0]), 6.0)
    assert dialogue_starts(shifted) == [4.0, 14.0]
    assert b"-->" in shifted


class TestFindReference:
    def test_an_embedded_track_is_trusted_and_preferred(self):
        with (
            patch.object(subtitle_timing, "_embedded_starts", return_value=(_speech(), "emb")),
            patch.object(subtitle_timing, "_sidecar_starts") as sidecars,
        ):
            ref = subtitle_timing.find_reference("/media/ep.mkv", "de")
        assert ref.trusted and ref.source == "emb"
        sidecars.assert_not_called()

    def test_a_sidecar_is_used_untrusted_without_an_embedded_track(self):
        with (
            patch.object(subtitle_timing, "_embedded_starts", return_value=None),
            patch.object(subtitle_timing, "_sidecar_starts", return_value=(_speech(), "side")),
        ):
            ref = subtitle_timing.find_reference("/media/ep.mkv", "de")
        assert not ref.trusted and ref.source == "side"

    def test_the_sidecar_of_the_searched_language_is_never_the_reference(self, tmp_path):
        video = tmp_path / "Show - S01E01.mkv"
        video.write_bytes(b"")
        (tmp_path / "Show - S01E01.de.srt").write_bytes(_srt(_speech(seed=5)))
        (tmp_path / "Show - S01E01.deu.srt").write_bytes(_srt(_speech(seed=6)))
        (tmp_path / "Show - S01E01.en.srt").write_bytes(_srt(_speech(seed=7)))
        (tmp_path / "Show - S01E01.en.forced.srt").write_bytes(_srt(_speech(400, seed=8)))
        with patch.object(subtitle_timing, "_embedded_starts", return_value=None):
            ref = subtitle_timing.find_reference(str(video), "de")
        assert ref.source.endswith(".en.srt")


def _result(sid: str, content: bytes) -> SubtitleResult:
    r = SubtitleResult(
        provider_name="animetosho", subtitle_id=sid, language="en", format="srt", score=280
    )
    r._test_content = content
    return r


def _download(r: SubtitleResult) -> bytes:
    r.content = r._test_content
    return r._test_content


class TestDownloadGate:
    def _run(self, results, reference: Reference | None):
        from providers.download_manager import search_and_download_best

        with (
            patch("subtitle_timing.find_reference", return_value=reference),
            patch("subtitle_plausibility.video_duration_s", return_value=DURATION),
            patch("providers.download_manager.decision_log") as dlog,
        ):
            best = search_and_download_best(
                search_fn=lambda *_a, **_kw: results,
                download_fn=_download,
                update_stats_fn=MagicMock(),
                query=VideoQuery(file_path="/media/ep.mkv"),
            )
        statuses = [c.args[2] for c in dlog.download_attempt.call_args_list]
        return best, statuses

    def test_a_track_for_another_cut_is_skipped_for_the_next(self):
        speech = _speech()
        wrong = _result("wrong", _srt(_translation_of(_speech(seed=99))))
        right = _result("right", _srt(_translation_of(speech)))
        best, statuses = self._run([wrong, right], Reference(speech, True, "emb"))
        assert best is right
        assert statuses == ["timing_mismatch", "selected"]

    def test_a_late_track_is_shifted_into_place(self):
        speech = _speech()
        late = _result("late", _srt(_translation_of(speech, offset=6.0)))
        best, statuses = self._run([late], Reference(speech, True, "emb"))
        assert best is late
        assert statuses == ["timing_shifted", "selected"]
        assert align(speech, dialogue_starts(best.content)).verdict == FIT

    def test_an_untrusted_reference_never_blocks_every_candidate(self):
        # The sidecar reference is itself the wrong one: all candidates
        # disagree with it, so the best candidate is taken anyway.
        bad_reference = Reference(_speech(seed=50), False, "sidecar x.en.srt")
        speech = _speech()
        first = _result("first", _srt(_translation_of(speech)))
        second = _result("second", _srt(_translation_of(speech, seed=3)))
        best, statuses = self._run([first, second], bad_reference)
        assert best is first
        assert statuses == ["timing_mismatch", "timing_mismatch", "selected"]

    def test_a_trusted_reference_refuses_every_wrong_candidate(self):
        speech = _speech()
        wrong = _result("wrong", _srt(_translation_of(_speech(seed=99))))
        best, statuses = self._run([wrong], Reference(speech, True, "emb"))
        assert best is None
        assert statuses == ["timing_mismatch"]

    def test_no_reference_changes_nothing(self):
        cand = _result("any", _srt(_speech(seed=99)))
        best, statuses = self._run([cand], None)
        assert best is cand
        assert statuses == ["selected"]
