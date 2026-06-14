"""Tests for dubtitle detection & selection (roadmap A4 / issue #146).

Covers the pure similarity primitives, Tier-1 heuristic classification,
the windowing maths, and the orchestrator's Tier-1/Tier-2 decision paths
with audio sampling mocked out (no ffmpeg/Whisper needed).
"""

from __future__ import annotations

import services.dubtitle.detector as det
from services.dubtitle.detector import (
    _classify_tier1,
    _compute_windows,
    _Cue,
    _cue_statistics,
    _english_subtitle_streams,
    _score_cues_against_windows,
    _TranscriptWindow,
    detect_dubtitle,
    validate_subtitle_against_audio,
)
from services.dubtitle.text_similarity import (
    containment_score,
    jaccard_score,
    normalize_to_tokens,
)

# ---------------------------------------------------------------------------
# text_similarity
# ---------------------------------------------------------------------------


class TestNormalizeToTokens:
    def test_strips_ass_override_blocks(self):
        assert normalize_to_tokens("{\\an8}hello {\\pos(1,2)}world") == ["hello", "world"]

    def test_strips_bracketed_sdh_by_default(self):
        assert normalize_to_tokens("[door creaks] run now") == ["run", "now"]

    def test_keeps_bracketed_when_disabled(self):
        toks = normalize_to_tokens("[door creaks] run", strip_bracketed=False)
        assert "door" in toks and "creaks" in toks

    def test_strips_speaker_labels_and_fillers(self):
        assert normalize_to_tokens("NARRATOR: uh well then") == ["well", "then"]

    def test_strips_music_notes_and_linebreaks(self):
        assert normalize_to_tokens("first\\Nsecond ♪") == ["first", "second"]

    def test_empty(self):
        assert normalize_to_tokens("") == []
        assert normalize_to_tokens("{\\an8}♪♪") == []


class TestSimilarityMetrics:
    def test_containment_is_asymmetric_fraction(self):
        sub = {"the", "quick", "brown", "fox"}
        transcript = {"a", "quick", "brown", "fox", "jumps"}
        assert containment_score(sub, transcript) == 0.75

    def test_containment_empty_sub_is_zero(self):
        assert containment_score(set(), {"a"}) == 0.0

    def test_dubtitle_scores_far_above_fansub(self):
        # Dub transcript tokens
        transcript = set(
            ["i", "will", "protect", "everyone", "no", "matter", "what", "it", "takes"]
        )
        dubtitle = set(["i", "will", "protect", "everyone", "no", "matter", "what"])
        fansub = set(["the", "bonds", "we", "share", "transcend", "mere", "obligation"])
        assert containment_score(dubtitle, transcript) >= 0.7
        assert containment_score(fansub, transcript) <= 0.4

    def test_jaccard_symmetric(self):
        assert jaccard_score({"a", "b"}, {"b", "c"}) == 1 / 3
        assert jaccard_score(set(), set()) == 0.0


# ---------------------------------------------------------------------------
# Tier-1 statistics + classification
# ---------------------------------------------------------------------------


def _dense_cues(
    n: int, *, gap_ms: int = 3000, text: str = "some spoken dialogue here"
) -> list[_Cue]:
    cues = []
    t = 0
    for _ in range(n):
        cues.append(_Cue(start_ms=t, end_ms=t + 2000, text=text))
        t += gap_ms
    return cues


class TestCueStatistics:
    def test_density_and_overlap(self):
        cues = _dense_cues(20)
        density, avg_cps, overlap = _cue_statistics(cues)
        assert density > 3.0
        assert avg_cps > 0
        assert overlap == 0.0

    def test_detects_overlap(self):
        cues = [
            _Cue(0, 5000, "one"),
            _Cue(3000, 8000, "two"),  # starts before previous ends
            _Cue(9000, 10000, "three"),
        ]
        _, _, overlap = _cue_statistics(cues)
        assert overlap > 0

    def test_empty(self):
        assert _cue_statistics([]) == (0.0, 0.0, 0.0)


class TestTier1Classification:
    def _stream(self, *, sub_index=0, title="", forced=False, sdh=False, lang="eng"):
        disp = {"forced": 1 if forced else 0}
        if sdh:
            disp["hearing_impaired"] = 1
        raw = {
            "index": 10 + sub_index,
            "tags": {"title": title, "language": lang},
            "disposition": disp,
        }
        return {
            "sub_index": sub_index,
            "format": "ass",
            "language": lang,
            "_tags": raw["tags"],
            "_raw": raw,
        }

    def test_forced_disposition_is_signs_forced(self):
        c = _classify_tier1(self._stream(forced=True), _dense_cues(50))
        assert c.tier1_label == "signs_forced"
        assert c.subtype == "forced"

    def test_signs_title_is_signs_forced(self):
        c = _classify_tier1(self._stream(title="Signs & Songs"), _dense_cues(50))
        assert c.tier1_label == "signs_forced"

    def test_sparse_track_is_sparse(self):
        c = _classify_tier1(self._stream(), _dense_cues(5))
        assert c.tier1_label == "sparse"

    def test_sdh_full_track_is_likely_dubtitle(self):
        c = _classify_tier1(self._stream(title="English CC", sdh=True), _dense_cues(80))
        assert c.tier1_label == "likely_dubtitle"
        assert c.is_sdh is True

    def test_plain_full_track_is_candidate(self):
        c = _classify_tier1(self._stream(title="English"), _dense_cues(80))
        assert c.tier1_label == "candidate"


class TestEnglishStreamFilter:
    def test_filters_english_text_streams_only(self):
        probe = {
            "streams": [
                {"codec_type": "audio", "codec_name": "aac", "tags": {"language": "eng"}},
                {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
                {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "jpn"}},
                {
                    "codec_type": "subtitle",
                    "codec_name": "hdmv_pgs_subtitle",
                    "tags": {"language": "eng"},
                },
                {"codec_type": "subtitle", "codec_name": "srt", "tags": {"language": "und"}},
            ]
        }
        out = _english_subtitle_streams(probe)
        langs = {s["language"] for s in out}
        # eng ass + und srt kept; jpn excluded; pgs (image) excluded
        assert langs == {"eng", "und"}
        # sub_index counts every subtitle stream, including the skipped pgs
        assert [s["sub_index"] for s in out] == [0, 3]


# ---------------------------------------------------------------------------
# Tier-2 windowing + scoring
# ---------------------------------------------------------------------------


class TestWindows:
    def test_three_windows_for_long_file(self):
        wins = _compute_windows(24 * 60 * 1000)
        assert len(wins) == 3
        assert all(end > start for start, end in wins)
        # OP/ED-avoiding: first window not at absolute zero for a long file
        assert wins[0][0] > 0

    def test_short_file_collapses(self):
        wins = _compute_windows(20 * 1000)
        assert len(wins) == 1
        assert wins[0] == (0, 20 * 1000)

    def test_zero_duration(self):
        assert _compute_windows(0) == []


class TestScoreCuesAgainstWindows:
    def test_scores_only_in_window_cues(self):
        windows = [_TranscriptWindow(0, 10_000, {"hello", "world", "run"})]
        cues = [
            _Cue(1000, 2000, "hello world"),  # in window, full match
            _Cue(50_000, 51_000, "totally different text"),  # out of window, ignored
        ]
        score = _score_cues_against_windows(cues, windows)
        assert score == 1.0

    def test_none_when_no_cues_in_window(self):
        windows = [_TranscriptWindow(0, 10_000, {"hello"})]
        cues = [_Cue(50_000, 51_000, "later")]
        assert _score_cues_against_windows(cues, windows) is None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class TestDetectDubtitle:
    def _probe(self, langs_codecs):
        return {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": codec,
                    "tags": {"language": lang, "title": title},
                }
                for lang, codec, title in langs_codecs
            ]
        }

    def test_no_english_tracks(self, monkeypatch):
        probe = {
            "streams": [
                {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "jpn"}}
            ]
        }
        res = detect_dubtitle("/fake.mkv", probe_data=probe, min_score=0.55)
        assert res.dubtitle_sub_index is None
        assert "No English" in res.message

    def test_single_full_text_track_tier1(self, monkeypatch):
        probe = self._probe([("eng", "ass", "English")])
        monkeypatch.setattr(det, "_extract_and_load_cues", lambda *a, **k: _dense_cues(80))
        res = detect_dubtitle("/fake.mkv", probe_data=probe, min_score=0.55)
        assert res.method == "tier1"
        assert res.dubtitle_sub_index == 0
        assert res.candidates[0].is_dubtitle is True

    def test_lone_sdh_wins_tier1(self, monkeypatch):
        probe = self._probe([("eng", "ass", "English"), ("eng", "ass", "English SDH")])
        monkeypatch.setattr(det, "_extract_and_load_cues", lambda *a, **k: _dense_cues(80))
        res = detect_dubtitle("/fake.mkv", probe_data=probe, min_score=0.55)
        assert res.method == "tier1"
        # SDH track is sub_index 1
        assert res.dubtitle_sub_index == 1

    def test_two_full_text_tracks_trigger_tier2(self, monkeypatch):
        probe = self._probe(
            [("eng", "ass", "English [GroupA]"), ("eng", "ass", "English [GroupB]")]
        )

        def fake_cues(video, sub_index, fmt):
            # Dense tracks (so Tier-1 = candidate), with distinct text in the
            # sampling window [720_000, 765_000].
            window_text = (
                "the bonds we share transcend obligation"
                if sub_index == 0  # fansub — diverges from the dub
                else "i will protect everyone no matter what"  # dubtitle — matches
            )
            cues = []
            for i in range(80):
                t = i * 10_000
                text = window_text if 720_000 <= t < 765_000 else "filler line here"
                cues.append(_Cue(t, t + 2_000, text))
            return cues

        monkeypatch.setattr(det, "_extract_and_load_cues", fake_cues)
        transcript = set(
            ["i", "will", "protect", "everyone", "no", "matter", "what", "it", "takes"]
        )
        monkeypatch.setattr(
            det,
            "_build_dub_transcript_windows",
            lambda video, dur: [_TranscriptWindow(720_000, 765_000, transcript)],
        )
        res = detect_dubtitle("/fake.mkv", probe_data=probe, min_score=0.55)
        assert res.method == "tier2"
        assert res.tier2_ran is True
        assert res.dubtitle_sub_index == 1
        assert res.candidates[1].audio_score >= 0.55
        assert res.candidates[0].audio_score < res.candidates[1].audio_score

    def test_tier2_unavailable_falls_back_gracefully(self, monkeypatch):
        probe = self._probe([("eng", "ass", "A"), ("eng", "ass", "B")])
        monkeypatch.setattr(det, "_extract_and_load_cues", lambda *a, **k: _dense_cues(80))
        monkeypatch.setattr(det, "_build_dub_transcript_windows", lambda video, dur: [])
        res = detect_dubtitle("/fake.mkv", probe_data=probe, min_score=0.55)
        assert res.method == "tier1"
        assert res.dubtitle_sub_index is None
        assert res.whisper_fallback_available is True

    def test_run_tier2_false_skips_audio(self, monkeypatch):
        probe = self._probe([("eng", "ass", "A"), ("eng", "ass", "B")])
        monkeypatch.setattr(det, "_extract_and_load_cues", lambda *a, **k: _dense_cues(80))
        called = {"n": 0}

        def _should_not_run(*a, **k):
            called["n"] += 1
            return []

        monkeypatch.setattr(det, "_build_dub_transcript_windows", _should_not_run)
        res = detect_dubtitle("/fake.mkv", probe_data=probe, min_score=0.55, run_tier2=False)
        assert called["n"] == 0
        assert res.dubtitle_sub_index is None
        assert res.whisper_fallback_available is True


class TestValidateSubtitleAgainstAudio:
    def test_pass_when_matches(self, monkeypatch, tmp_path):
        sub = tmp_path / "x.srt"
        sub.write_text(
            "1\n00:12:00,000 --> 00:12:02,000\ni will protect everyone no matter what\n",
            encoding="utf-8",
        )
        transcript = set(
            ["i", "will", "protect", "everyone", "no", "matter", "what", "it", "takes"]
        )
        monkeypatch.setattr(
            det,
            "_build_dub_transcript_windows",
            lambda video, dur: [_TranscriptWindow(720_000, 765_000, transcript)],
        )
        res = validate_subtitle_against_audio("/fake.mkv", str(sub), min_score=0.55)
        assert res.passed is True
        assert res.score >= 0.55

    def test_fail_when_mismatch(self, monkeypatch, tmp_path):
        sub = tmp_path / "x.srt"
        sub.write_text(
            "1\n00:12:00,000 --> 00:12:02,000\nthe bonds we share transcend obligation\n",
            encoding="utf-8",
        )
        transcript = set(
            ["i", "will", "protect", "everyone", "no", "matter", "what", "it", "takes"]
        )
        monkeypatch.setattr(
            det,
            "_build_dub_transcript_windows",
            lambda video, dur: [_TranscriptWindow(720_000, 765_000, transcript)],
        )
        res = validate_subtitle_against_audio("/fake.mkv", str(sub), min_score=0.55)
        assert res.passed is False

    def test_unverifiable_does_not_block(self, monkeypatch, tmp_path):
        sub = tmp_path / "x.srt"
        sub.write_text("1\n00:12:00,000 --> 00:12:02,000\nhello\n", encoding="utf-8")
        monkeypatch.setattr(det, "_build_dub_transcript_windows", lambda video, dur: [])
        res = validate_subtitle_against_audio("/fake.mkv", str(sub), min_score=0.55)
        assert res.passed is False
        assert "skipped" in res.message.lower()
