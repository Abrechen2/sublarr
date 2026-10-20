"""A subtitle whose time span does not fit the video is not that video's subtitle.

Prod 2026-10 (Clevatess): a 787-event ASS ending at 2738 s — the BD
double-length episode 1 — was saved for a 1420 s episode, and ffsubsync then
"aligned" it by -5 s. The download loop now rejects such a candidate and tries
the next one, and the sync refuses to time a file that overruns its video.
"""

import time
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from subtitle_plausibility import length_mismatch, subtitle_span, video_duration_s


def _ts(seconds: float, sep: str = ",") -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _srt(spans: list[tuple[float, float]]) -> bytes:
    blocks = [f"{i}\n{_ts(a)} --> {_ts(b)}\nLine {i}\n" for i, (a, b) in enumerate(spans, 1)]
    return "\n".join(blocks).encode()


def _ass_ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass(spans: list[tuple[float, float]], comments: list[tuple[float, float]] = ()) -> bytes:
    head = (
        "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [f"Dialogue: 0,{_ass_ts(a)},{_ass_ts(b)},Default,,0,0,0,,Hi" for a, b in spans]
    lines += [f"Comment: 0,{_ass_ts(a)},{_ass_ts(b)},Default,,0,0,0,,note" for a, b in comments]
    return (head + "\n".join(lines) + "\n").encode()


def _evenly(n: int, end: float, start: float = 5.0) -> list[tuple[float, float]]:
    step = (end - start) / n
    return [(start + i * step, start + i * step + min(2.0, step)) for i in range(n)]


DURATION = 1420.0


class TestSpan:
    def test_ass_dialogue_only(self):
        span = subtitle_span(_ass([(1.0, 2.5), (100.0, 104.0)], comments=[(0.0, 9000.0)]))
        assert span.first_start == pytest.approx(1.0)
        assert span.last_end == pytest.approx(104.0)
        assert span.events == 2

    def test_srt(self):
        span = subtitle_span(_srt([(3.0, 4.0), (1300.5, 1302.25)]))
        assert span.first_start == pytest.approx(3.0)
        assert span.last_end == pytest.approx(1302.25)

    def test_unparseable_is_none(self):
        assert subtitle_span(b"not a subtitle at all") is None

    @pytest.mark.parametrize(
        "content",
        [
            b"1" * 5_000_000,
            b"," * 5_000_000,
            b"Dialogue:" + b"," * 5_000_000,
            b"Dialogue: " + b"1:" * 2_000_000,
            (b"00:00:01,000 " * 400_000) + b"-->",
            b"1:00:00,000 --> " * 300_000,
            b"Dialogue: 0," * 400_000,
        ],
        ids=["digits", "commas", "dialogue-commas", "dialogue-colons", "srt-long", "arrows", "dlg"],
    )
    def test_pathological_input_finishes_quickly(self, content):
        """Provider content is untrusted (up to 20 MB): the scan must stay linear."""
        start = time.perf_counter()
        subtitle_span(content)
        assert time.perf_counter() - start < 1.0

    def test_many_lines_finish_quickly(self):
        content = b"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,x\n" * 300_000
        start = time.perf_counter()
        span = subtitle_span(content)
        assert time.perf_counter() - start < 2.0
        assert span.events == 200_000


class TestLengthMismatch:
    def test_double_length_episode_is_rejected(self):
        """The prod case: 787 events ending at 2738 s on a 1420 s video."""
        content = _ass(_evenly(787, 2736.0))
        reason = length_mismatch(content, DURATION, partial_ok=False)
        assert reason and "787 events" in reason and "1420 s" in reason

    def test_a_fitting_subtitle_passes(self):
        assert length_mismatch(_srt(_evenly(300, 1400.0)), DURATION, partial_ok=False) is None

    def test_overrun_within_tolerance_passes(self):
        """max(10 %, 120 s) — trailing credits or a slightly longer cut."""
        assert length_mismatch(_srt(_evenly(300, 1530.0)), DURATION, partial_ok=False) is None

    def test_a_single_stray_late_event_is_not_an_overrun(self):
        spans = _evenly(300, 1400.0) + [(35999.0, 36000.0)]
        assert length_mismatch(_srt(spans), DURATION, partial_ok=False) is None

    def test_half_coverage_is_rejected(self):
        reason = length_mismatch(_srt(_evenly(200, 600.0)), DURATION, partial_ok=False)
        assert reason and "cover" in reason

    def test_forced_or_signs_may_cover_little(self):
        assert length_mismatch(_srt(_evenly(200, 600.0)), DURATION, partial_ok=True) is None

    def test_partial_subtitles_still_get_the_overrun_check(self):
        assert length_mismatch(_ass(_evenly(787, 2736.0)), DURATION, partial_ok=True)

    def test_unknown_duration_checks_nothing(self):
        assert length_mismatch(_ass(_evenly(787, 2736.0)), None, partial_ok=False) is None
        assert length_mismatch(_ass(_evenly(787, 2736.0)), 0.0, partial_ok=False) is None


class TestVideoDuration:
    def test_reads_the_cached_probe(self, tmp_path):
        video = tmp_path / "ep.mkv"
        video.touch()
        probe = {"streams": [{"codec_type": "video", "tags": {"DURATION": "00:23:40.000000000"}}]}
        with patch("ass_probe.get_media_streams", return_value=probe):
            assert video_duration_s(str(video)) == pytest.approx(1420.0)

    def test_unknown_when_the_probe_has_no_video_length(self, tmp_path):
        video = tmp_path / "ep.mkv"
        video.touch()
        with patch("ass_probe.get_media_streams", return_value={"streams": []}):
            assert video_duration_s(str(video)) is None

    def test_unknown_when_the_probe_fails(self, tmp_path):
        video = tmp_path / "ep.mkv"
        video.touch()
        with patch("ass_probe.get_media_streams", side_effect=RuntimeError("ffprobe failed")):
            assert video_duration_s(str(video)) is None

    def test_missing_file_is_unknown(self, tmp_path):
        assert video_duration_s(str(tmp_path / "gone.mkv")) is None


def _result(sid: str, content: bytes, **kw) -> SubtitleResult:
    r = SubtitleResult(provider_name="animetosho", subtitle_id=sid, language="de", **kw)
    r.format = SubtitleFormat.ASS
    r._test_content = content  # served by the fake download_fn below
    return r


class TestDownloadLoop:
    def _run(self, results, query, *, probe=True):
        from providers.download_manager import search_and_download_best

        stats = MagicMock()
        duration = (
            patch("subtitle_plausibility.video_duration_s", return_value=DURATION)
            if probe
            else nullcontext()
        )
        with duration, patch("providers.download_manager.decision_log") as dlog:
            best = search_and_download_best(
                search_fn=lambda *_a, **_kw: results,
                download_fn=lambda r: r._test_content,
                update_stats_fn=stats,
                query=query,
            )
        return best, dlog, stats

    def test_overrunning_candidate_is_skipped_for_the_next(self, tmp_path):
        wrong = _result("bd-ep1", _ass(_evenly(787, 2736.0)))
        right = _result("tv-ep1", _ass(_evenly(300, 1400.0)))
        query = VideoQuery(file_path=str(tmp_path / "ep.mkv"))

        best, dlog, stats = self._run([wrong, right], query)

        assert best is right
        statuses = [c.args[2] for c in dlog.download_attempt.call_args_list]
        assert statuses == ["length_mismatch", "selected"]
        # Not the provider's fault in the sense of a broken download: no
        # failure booked against its stats for the rejected file.
        assert all(c.kwargs.get("success", True) for c in stats.call_args_list)

    def test_forced_search_skips_the_coverage_check(self, tmp_path):
        signs = _result("signs", _ass(_evenly(40, 600.0)))
        query = VideoQuery(file_path=str(tmp_path / "ep.mkv"), forced_only=True)

        best, _, _ = self._run([signs], query)

        assert best is signs

    def test_a_signs_release_skips_the_coverage_check(self, tmp_path):
        signs = _result("signs", _ass(_evenly(40, 600.0)), release_info="[Group] Show - 01 [Signs]")
        query = VideoQuery(file_path=str(tmp_path / "ep.mkv"))

        best, _, _ = self._run([signs], query)

        assert best is signs

    def test_without_a_video_path_nothing_is_checked(self):
        wrong = _result("bd-ep1", _ass(_evenly(787, 2736.0)))

        best, _, _ = self._run([wrong], VideoQuery(), probe=False)

        assert best is wrong


class TestSyncRecheck:
    def test_sync_refuses_a_subtitle_that_overruns_its_video(self, tmp_path):
        from services.video_sync import (
            SubtitleLengthMismatchError,
            SyncSanityThresholdError,
            sync_with_ffsubsync,
        )

        sub = tmp_path / "ep.de.ass"
        original = _ass(_evenly(787, 2736.0))
        sub.write_bytes(original)
        run = MagicMock()
        with (
            patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
            patch("services.video_sync.subprocess.run", run),
            patch("subtitle_plausibility.video_duration_s", return_value=DURATION),
            pytest.raises(SubtitleLengthMismatchError) as exc,
        ):
            sync_with_ffsubsync(str(sub), str(tmp_path / "ep.mkv"))
        assert isinstance(exc.value, SyncSanityThresholdError)
        run.assert_not_called()
        assert sub.read_bytes() == original

    def test_sync_does_not_judge_coverage(self, tmp_path):
        """A partial subtitle can still be shifted — only an overrun is refused."""
        from services.video_sync import sync_with_ffsubsync

        sub = tmp_path / "ep.de.srt"
        sub.write_bytes(_srt(_evenly(50, 600.0)))
        fake = MagicMock(returncode=0, stderr="INFO     offset seconds: 0.250", stdout="")
        with (
            patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
            patch("services.video_sync.subprocess.run", return_value=fake),
            patch("subtitle_plausibility.video_duration_s", return_value=DURATION),
            patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        ):
            assert sync_with_ffsubsync(str(sub), str(tmp_path / "ep.mkv"))["shift_ms"] == 250
