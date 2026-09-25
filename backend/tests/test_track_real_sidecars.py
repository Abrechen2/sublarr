"""Only genuine subtitles make an embedded track redundant (policy B)."""

from datetime import UTC, datetime, timedelta

from services.foreign_tracks.sidecars import real_sidecar_languages

_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n"
_HTML_404 = (
    "<html><head><title>404 Not Found</title></head>"
    "<body><h1>404 Not Found</h1><p>nginx</p></body></html>"
)


def _record(video, lang, *, source, provider="opensubtitles", age_s=0):
    from db.models.providers import SubtitleDownload
    from extensions import db

    db.session.add(
        SubtitleDownload(
            provider_name=provider,
            subtitle_id="x",
            language=lang,
            format="srt",
            file_path=str(video),
            score=100,
            source=source,
            downloaded_at=datetime.now(UTC) - timedelta(seconds=age_s),
        )
    )
    db.session.commit()


def _record_origin(video, lang, *, origin="extraction", age_s=0):
    from db.models.providers import SidecarOrigin
    from extensions import db

    db.session.add(
        SidecarOrigin(
            video_path=str(video),
            language=lang,
            origin=origin,
            recorded_at=datetime.now(UTC) - timedelta(seconds=age_s),
        )
    )
    db.session.commit()


def _setup(tmp_path, name="Show - S01E01.de.srt", text=_SRT):
    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"v")
    (tmp_path / name).write_text(text, encoding="utf-8")
    return video


def test_a_provider_download_counts(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record(video, "de", source="provider")
    assert real_sidecar_languages(str(video), {"de", "en"}) == {"de"}


def test_a_machine_translation_never_counts(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record(video, "de", source="machine_translation", provider="translation")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_unknown_origin_does_not_count(app_ctx, tmp_path):
    video = _setup(tmp_path)
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_latest_record_decides_when_mt_replaced_a_real_download(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record(video, "de", source="provider", age_s=3600)
    _record(video, "de", source="machine_translation", provider="translation")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_an_empty_sidecar_does_not_count(app_ctx, tmp_path):
    video = _setup(tmp_path, text="")
    _record(video, "de", source="provider")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_an_alias_name_counts(app_ctx, tmp_path):
    """Extraction provenance now lives in sidecar_origins, not subtitle_downloads."""
    video = _setup(tmp_path, name="Show - S01E01.ger.srt")
    _record_origin(video, "de")
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def test_a_forced_sidecar_is_not_a_main_track(app_ctx, tmp_path):
    video = _setup(tmp_path, name="Show - S01E01.de.forced.srt")
    _record(video, "de", source="provider")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_extraction_writes_a_sidecar_origin_row_not_a_download(app_ctx, tmp_path):
    """Without a sidecar_origins row, extracted sidecars could never count under
    policy B. It must NOT go through subtitle_downloads — that table backs
    dashboard counts / average score / stats that a firehose of extraction
    rows would skew (ruling 2026-09-25).
    """
    import services.embedded_extractor as ex
    from db.models.providers import SidecarOrigin, SubtitleDownload
    from extensions import db

    video = tmp_path / "Show - S01E01.mkv"
    ex._record_extraction(str(video), "de", "srt")

    origins = db.session.query(SidecarOrigin).filter_by(video_path=str(video)).all()
    assert len(origins) == 1
    assert origins[0].language == "de"
    assert origins[0].origin == "extraction"

    downloads = db.session.query(SubtitleDownload).filter_by(file_path=str(video)).all()
    assert downloads == []


def test_an_extraction_origin_makes_the_language_count(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record_origin(video, "de")
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def test_a_newer_mt_download_after_extraction_uncounts_it(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record_origin(video, "de", age_s=3600)
    _record(video, "de", source="machine_translation", provider="translation")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_an_extraction_newer_than_an_mt_download_counts(app_ctx, tmp_path):
    video = _setup(tmp_path)
    _record(video, "de", source="machine_translation", provider="translation", age_s=3600)
    _record_origin(video, "de")
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def test_a_garbage_sidecar_with_a_history_record_does_not_count(app_ctx, tmp_path):
    """A real history record does not make a garbage file (e.g. an HTML error
    page saved under a subtitle extension) a real sidecar — the WHOLE file
    content must pass the same validation save_subtitle applies to a fresh
    download.
    """
    video = _setup(tmp_path, text=_HTML_404)
    _record(video, "de", source="provider")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_a_read_error_is_not_usable(app_ctx, tmp_path, monkeypatch):
    video = _setup(tmp_path)
    _record(video, "de", source="provider")

    import services.foreign_tracks.sidecars as sc

    def _boom(*_a, **_kw):
        raise OSError("disk error")

    monkeypatch.setattr(sc, "open", _boom, raising=False)
    assert real_sidecar_languages(str(video), {"de"}) == set()
