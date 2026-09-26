"""Final-review C1: provenance must match the sidecar actually found.

History is keyed by (video, language), not by the sidecar file. A record that
describes a DIFFERENT file than the one on disk — a forced download, a
download in another format, or a sidecar a non-recording writer replaced
afterwards — must never make a hand-placed or machine-written sidecar count
as "real" (spec 2026-09-25 §4: unknown origin never counts).
"""

import os
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from services.foreign_tracks.sidecars import real_sidecar_languages

_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


def _record(video, lang, *, fmt="srt", subtitle_type="full", age_s=0, source="provider"):
    from db.models.providers import SubtitleDownload
    from extensions import db

    db.session.add(
        SubtitleDownload(
            provider_name="opensubtitles",
            subtitle_id="x",
            language=lang,
            format=fmt,
            file_path=str(video),
            score=100,
            source=source,
            subtitle_type=subtitle_type,
            downloaded_at=datetime.now(UTC) - timedelta(seconds=age_s),
        )
    )
    db.session.commit()


def _setup(tmp_path, name="Show - S01E01.de.srt", mtime_age_s=None):
    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"v")
    sidecar = tmp_path / name
    sidecar.write_text(_SRT, encoding="utf-8")
    if mtime_age_s is not None:
        stamp = time.time() - mtime_age_s
        os.utime(sidecar, (stamp, stamp))
    return video


# --- forced rows -------------------------------------------------------------


def test_record_subtitle_download_stores_the_subtitle_type(app_ctx):
    from db.models.providers import SubtitleDownload
    from db.providers import record_subtitle_download
    from extensions import db

    record_subtitle_download(
        "opensubtitles", "x", "de", "srt", "/m/v.mkv", 10, subtitle_type="forced"
    )
    row = db.session.query(SubtitleDownload).filter_by(file_path="/m/v.mkv").one()
    assert row.subtitle_type == "forced"


def test_record_subtitle_download_defaults_to_full(app_ctx):
    from db.models.providers import SubtitleDownload
    from db.providers import record_subtitle_download
    from extensions import db

    record_subtitle_download("opensubtitles", "x", "de", "srt", "/m/w.mkv", 10)
    row = db.session.query(SubtitleDownload).filter_by(file_path="/m/w.mkv").one()
    assert row.subtitle_type == "full"


def test_a_forced_download_does_not_make_a_hand_placed_sidecar_real(app_ctx, tmp_path):
    video = _setup(tmp_path)  # hand-placed .de.srt, no record of its own
    _record(video, "de", subtitle_type="forced")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_a_forced_row_newer_than_a_real_download_does_not_hide_it(app_ctx, tmp_path):
    video = _setup(tmp_path, mtime_age_s=3600)
    _record(video, "de", age_s=3590)
    _record(video, "de", subtitle_type="forced")
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def _run_forced_item(monkeypatch, captured):
    import wanted_search.post_processor as pp
    from providers.base import SubtitleFormat

    result = SimpleNamespace(
        content=b"x",
        format=SubtitleFormat.SRT,
        provider_name="opensubtitles",
        subtitle_id="s1",
        score=50,
        score_breakdown=None,
    )
    manager = SimpleNamespace(
        search_and_download_best=lambda query, format_filter=None: result,
        save_subtitle=lambda res, path, **kw: path,
    )
    monkeypatch.setattr(pp, "build_query_from_wanted", lambda item: SimpleNamespace())
    monkeypatch.setattr(pp, "delete_wanted_item", lambda item_id: None)
    monkeypatch.setattr(pp, "record_subtitle_download", lambda *a, **kw: captured.append((a, kw)))
    item = {"file_path": "/m/Show - S01E01.mkv", "sonarr_series_id": 1}
    return pp._process_forced_wanted_item(item, 7, "de", manager)


def test_the_forced_wanted_path_records_its_download_as_forced(app_ctx, monkeypatch):
    captured = []
    out = _run_forced_item(monkeypatch, captured)
    assert out["status"] == "found"
    assert len(captured) == 1
    assert captured[0][1].get("subtitle_type") == "forced"


def test_a_manual_forced_upload_is_recorded_as_forced(app_ctx, tmp_path, monkeypatch):
    import db.providers as dbp
    from services.subtitle_upload import save_manual_subtitle

    captured = []
    monkeypatch.setattr(dbp, "record_subtitle_download", lambda *a, **kw: captured.append(kw))
    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"v")
    save_manual_subtitle(str(video), _SRT.encode(), "srt", "de", "forced", False, [str(tmp_path)])
    assert captured and captured[0].get("subtitle_type") == "forced"


# --- format must match -------------------------------------------------------


def test_a_real_ass_download_does_not_vouch_for_a_hand_placed_srt(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record(video, "de", fmt="ass")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_a_real_srt_download_counts_for_the_srt_sidecar(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record(video, "de", fmt="srt")
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


# --- a non-recording writer replaced the sidecar ---------------------------


def test_a_sidecar_rewritten_after_its_record_is_unknown(app_ctx, tmp_path):
    """translate_file, batch, translation_jobs and the sidecar_translate drain
    replace sidecars without writing history — the file on disk is then newer
    than the record that described its predecessor."""
    video = _setup(tmp_path)  # mtime: now
    _record(video, "de", age_s=600)  # the record describes a file from 10 min ago
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_a_sidecar_written_moments_before_its_record_counts(app_ctx, tmp_path):
    video = _setup(tmp_path, mtime_age_s=30)
    _record(video, "de", age_s=0)
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def test_the_60s_grace_covers_post_processing_after_the_record(app_ctx, tmp_path):
    video = _setup(tmp_path)  # mtime: now
    _record(video, "de", age_s=45)
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def test_an_extraction_origin_is_also_guarded_by_mtime(app_ctx, tmp_path):
    from db.models.providers import SidecarOrigin
    from extensions import db

    video = _setup(tmp_path)
    db.session.add(
        SidecarOrigin(
            video_path=str(video),
            language="de",
            origin="extraction",
            recorded_at=datetime.now(UTC) - timedelta(seconds=900),
        )
    )
    db.session.commit()
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_an_extraction_origin_does_not_vouch_for_an_older_hand_placed_file(app_ctx, tmp_path):
    """sidecar_origins has no format column, so an extraction record is tied to
    the file it wrote by time: the extractor records right after writing. A
    .de.srt that was on disk hours before the extraction (which wrote a
    .de.ass) is not the file the record describes."""
    from db.models.providers import SidecarOrigin
    from extensions import db

    video = _setup(tmp_path, mtime_age_s=7200)
    db.session.add(
        SidecarOrigin(
            video_path=str(video),
            language="de",
            origin="extraction",
            recorded_at=datetime.now(UTC),
        )
    )
    db.session.commit()
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_a_download_does_not_vouch_for_a_much_older_file(app_ctx, tmp_path):
    """Final-review residual: a download row had no lower mtime bound. A file
    with a preserved old mtime (copied in by hand, restored from a backup)
    that sits where the download landed is not the downloaded file."""
    video = _setup(tmp_path, mtime_age_s=2 * 86400)
    _record(video, "de", age_s=0)
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_a_download_written_minutes_before_its_record_still_counts(app_ctx, tmp_path):
    """Post-processing (sync, normalise) can sit between save and record."""
    video = _setup(tmp_path, mtime_age_s=5 * 60)
    _record(video, "de", age_s=0)
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}
