"""Final-review I1: extraction origins must be recorded in a form the
real-sidecar check can find, and only for full dialogue tracks.

Driven through ``collect_subtitle_streams`` + ``extract_streams`` (the
production path of ``extract_and_cleanup``), not ``_record_extraction``
directly — calling the recorder by hand with "de" hid that the extractor
passed the raw container tag ("ger").
"""

from __future__ import annotations

_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n\n"


def _fake_extract(stream_info, out):
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(_SRT)


def _run(tmp_path, monkeypatch, streams):
    import services.embedded_extractor as ee

    mkv = str(tmp_path / "Show - S01E01.mkv")
    with open(mkv, "wb") as fh:
        fh.write(b"\x00")
    monkeypatch.setattr(
        "ass_utils.extract_subtitle_stream",
        lambda path, info, out: _fake_extract(info, out),
    )
    sub_streams = ee.collect_subtitle_streams({"streams": streams})
    ee.extract_streams(mkv, sub_streams, log_label="test")
    return mkv


def _origins(mkv):
    from db.models.providers import SidecarOrigin
    from extensions import db

    return db.session.query(SidecarOrigin).filter_by(video_path=mkv).all()


def test_an_extracted_ger_track_is_recorded_under_the_2_letter_code(app_ctx, tmp_path, monkeypatch):
    mkv = _run(
        tmp_path,
        monkeypatch,
        [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "ger"},
            }
        ],
    )
    assert [o.language for o in _origins(mkv)] == ["de"]


def test_an_extracted_ger_track_counts_as_a_real_sidecar(app_ctx, tmp_path, monkeypatch):
    from services.foreign_tracks.sidecars import real_sidecar_languages

    mkv = _run(
        tmp_path,
        monkeypatch,
        [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "ger"},
            }
        ],
    )
    assert real_sidecar_languages(mkv, {"de"}) == {"de"}


def test_an_extracted_signs_track_is_not_recorded(app_ctx, tmp_path, monkeypatch):
    """A signs-only sidecar must never make the full embedded track removable."""
    mkv = _run(
        tmp_path,
        monkeypatch,
        [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "ger", "title": "Signs & Songs"},
            }
        ],
    )
    assert _origins(mkv) == []


def test_an_extracted_forced_track_is_not_recorded(app_ctx, tmp_path, monkeypatch):
    mkv = _run(
        tmp_path,
        monkeypatch,
        [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "ger"},
                "disposition": {"forced": 1},
            }
        ],
    )
    assert _origins(mkv) == []
