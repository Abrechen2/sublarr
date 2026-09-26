"""The tie-break count never reads a whole file (measured on prod 2026-09-26).

The foreign-track sweep counted subtitle packets with ``ffprobe -count_packets``
on every tied file, which reads the WHOLE file: 5 minutes for one 44 GB
remux, so the probe phase over 21 066 files would have taken weeks. mkvmerge
already writes the same number into every MKV track's statistics tags
(``NUMBER_OF_FRAMES``), which the stream probe returns for free. Only when a
subtitle stream lacks the tag is a short sample from the start counted.
"""

import json
from types import SimpleNamespace


def _stream(index, frames=None, key="NUMBER_OF_FRAMES"):
    tags = {"language": "eng"}
    if frames is not None:
        tags[key] = str(frames)
    return {
        "index": index,
        "codec_type": "subtitle",
        "codec_name": "hdmv_pgs_subtitle",
        "tags": tags,
    }


def _no_subprocess(monkeypatch, ec):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"streams": []}), stderr="")

    monkeypatch.setattr(ec.subprocess, "run", fake_run)
    monkeypatch.setattr(ec, "_which", lambda cmd: True)
    return calls


def test_statistics_tags_answer_without_reading_the_file(monkeypatch):
    import remux.event_count as ec

    calls = _no_subprocess(monkeypatch, ec)
    counter = ec.make_event_counter("/m/thor.mkv", streams=[_stream(9, 2020), _stream(10, 10)])
    assert counter(9) == 2020
    assert counter(10) == 10
    assert calls == [], "the statistics tags are the count; nothing is read"


def test_language_suffixed_statistics_tags_are_read(monkeypatch):
    import remux.event_count as ec

    calls = _no_subprocess(monkeypatch, ec)
    counter = ec.make_event_counter(
        "/m/e1.mkv",
        streams=[_stream(2, 731, "NUMBER_OF_FRAMES-eng"), _stream(3, 757, "NUMBER_OF_FRAMES-eng")],
    )
    assert (counter(2), counter(3)) == (731, 757)
    assert calls == []


def test_a_missing_tag_counts_a_short_sample_never_the_whole_file(monkeypatch):
    """Mixing whole-file tag counts with a partial sample would compare apples
    with oranges, so one missing tag makes the whole file use the sample."""
    import remux.event_count as ec

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        payload = {
            "streams": [
                {"index": 2, "nb_read_packets": "12"},
                {"index": 3, "nb_read_packets": "80"},
            ]
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(ec.subprocess, "run", fake_run)
    monkeypatch.setattr(ec, "_which", lambda cmd: True)
    counter = ec.make_event_counter("/m/e1.mkv", streams=[_stream(2, 500), _stream(3)])
    assert (counter(2), counter(3)) == (12, 80)
    assert len(calls) == 1
    assert "-read_intervals" in calls[0], "only the start of the file is read"


def test_without_stream_data_the_sample_is_used(monkeypatch):
    import remux.event_count as ec

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [{"index": 4, "nb_read_packets": "7"}]}),
            stderr="",
        )

    monkeypatch.setattr(ec.subprocess, "run", fake_run)
    monkeypatch.setattr(ec, "_which", lambda cmd: True)
    counter = ec.make_event_counter("/m/e1.mkv")
    assert counter(4) == 7
    assert "-read_intervals" in calls[0]


def test_a_garbage_tag_falls_back_to_the_sample(monkeypatch):
    import remux.event_count as ec

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [{"index": 2, "nb_read_packets": "3"}]}),
            stderr="",
        )

    monkeypatch.setattr(ec.subprocess, "run", fake_run)
    monkeypatch.setattr(ec, "_which", lambda cmd: True)
    counter = ec.make_event_counter("/m/e1.mkv", streams=[_stream(2, "n/a")])
    assert counter(2) == 3
    assert len(calls) == 1


def test_production_callers_pass_the_probed_streams(monkeypatch):
    """Remux, sweep and preview already hold the probe — the counter must get it,
    otherwise every tie still pays for the sample read."""
    import remux
    from services.foreign_tracks import sweep as sw
    from services.foreign_tracks.select import TrackPolicy

    seen = []

    def make(path, streams=None):
        seen.append(streams)
        return lambda index: {2: 10, 3: 500}.get(index, 0)

    probe = {"streams": [_stream(2, 10), _stream(3, 500)]}
    monkeypatch.setattr(remux, "make_event_counter", make)
    sw._verdicts_for("/m/e1.mkv", probe, {"en", "eng"}, False, TrackPolicy(mode="one_per_language"))
    assert seen and seen[0] == probe["streams"]
