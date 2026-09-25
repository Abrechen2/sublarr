"""Final-review I3: the dialogue-events tie-break is wired in production.

``select_tracks(count_events=...)`` breaks a tie between two equally ranked
main tracks by their subtitle packet count. The remux strip, the sweep and
the preview now pass a memoised per-file counter; it is only consulted on a
tie and costs at most one ffprobe per file.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from services.foreign_tracks.select import TrackPolicy

_ONE = TrackPolicy(mode="one_per_language")

# Two equally ranked English full tracks (same format, neither default).
_TIED = {
    "streams": [
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
        {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
    ]
}
# No tie: ass outranks srt.
_UNTIED = {
    "streams": [
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
        {"index": 3, "codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
    ]
}


class _FakeCounter:
    def __init__(self, counts):
        self.counts = counts
        self.calls = []

    def __call__(self, index):
        self.calls.append(index)
        return self.counts.get(index, 0)


def _factory(counter):
    made = []

    def make(path):
        made.append(path)
        return counter

    return make, made


# --- the counter itself --------------------------------------------------------


def _ffprobe_ok(payload):
    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


def test_the_counter_runs_ffprobe_once_per_file_and_lazily(monkeypatch):
    import remux.event_count as ec

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _ffprobe_ok(
            {
                "streams": [
                    {"index": 2, "nb_read_packets": "40"},
                    {"index": 3, "nb_read_packets": "900"},
                ]
            }
        )

    monkeypatch.setattr(ec.subprocess, "run", fake_run)
    monkeypatch.setattr(ec, "_which", lambda cmd: True)
    counter = ec.make_event_counter("/m/e1.mkv")
    assert calls == [], "nothing is read until a tie asks for it"
    assert counter(2) == 40
    assert counter(3) == 900
    assert counter(2) == 40
    assert len(calls) == 1
    assert "-count_packets" in calls[0]


def test_an_ffprobe_failure_counts_zero_with_a_warning(monkeypatch, caplog):
    import remux.event_count as ec

    monkeypatch.setattr(
        ec.subprocess,
        "run",
        lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    monkeypatch.setattr(ec, "_which", lambda cmd: True)
    caplog.set_level(logging.WARNING)
    counter = ec.make_event_counter("/m/e1.mkv")
    assert counter(2) == 0
    assert counter(3) == 0
    assert any("packet" in r.message.lower() for r in caplog.records)


def test_zero_counts_fall_back_to_the_lower_index():
    from services.foreign_tracks.select import select_tracks

    verdicts = select_tracks(_TIED["streams"], _ONE, {"en", "eng"}, False, set(), lambda i: 0)
    assert [v.keep for v in verdicts] == [True, False]


# --- remux ---------------------------------------------------------------------


def _strip(probe, counter):
    import remux

    captured = {}
    make, made = _factory(counter)

    def fake_remove(*, video_path, streams, **kw):
        captured["streams"] = streams
        return "/bak"

    with (
        patch.object(remux, "make_event_counter", make),
        patch.object(remux, "get_media_streams", return_value=probe),
        patch.object(remux, "check_hardlink_policy", return_value=True),
        patch.object(remux, "remove_subtitle_streams", side_effect=fake_remove),
    ):
        remux.remove_foreign_subtitle_streams(
            video_path="/m/e1.mkv", target_languages={"en", "eng"}, policy=_ONE
        )
    return {i for i, _ in captured.get("streams", [])}


def test_remux_breaks_a_tie_by_packet_count():
    counter = _FakeCounter({2: 10, 3: 500})
    assert _strip(_TIED, counter) == {2}, "the track with more events is the main one"
    assert set(counter.calls) == {2, 3}


def test_remux_never_counts_without_a_tie():
    counter = _FakeCounter({2: 10_000, 3: 1})
    assert _strip(_UNTIED, counter) == {2}, "ass outranks srt; counts are irrelevant"
    assert counter.calls == []


# --- sweep ---------------------------------------------------------------------


def test_the_sweep_verdicts_use_the_counter():
    import remux
    from services.foreign_tracks import sweep as sw

    counter = _FakeCounter({2: 10, 3: 500})
    make, made = _factory(counter)
    with patch.object(remux, "make_event_counter", make):
        verdicts = sw._verdicts_for("/m/e1.mkv", _TIED, {"en", "eng"}, False, _ONE)
    assert [v["keep"] for v in verdicts] == [False, True]
    assert made == ["/m/e1.mkv"]


# --- preview -------------------------------------------------------------------


def test_the_preview_uses_the_counter(client, tmp_path, monkeypatch):
    import remux

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    counter = _FakeCounter({2: 10, 3: 500})
    make, made = _factory(counter)
    with (
        patch.object(remux, "make_event_counter", make),
        patch.object(remux, "get_media_streams", return_value=_TIED),
        patch("services.foreign_tracks.policy.resolve_policy", return_value=_ONE),
        patch("services.foreign_track_cleanup.cleanup_keep_languages", return_value={"en"}),
    ):
        resp = client.post("/api/v1/foreign-tracks/preview-file", json={"path": str(video)})
    assert resp.status_code == 200, resp.get_json()
    keep = {v["index"]: v["keep"] for v in resp.get_json()["verdicts"]}
    assert keep == {2: False, 3: True}
