"""Only genuine subtitles make an embedded track redundant (policy B)."""

from datetime import UTC, datetime, timedelta

from services.foreign_tracks.sidecars import real_sidecar_languages

_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


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
    video = _setup(tmp_path, name="Show - S01E01.ger.srt")
    _record(video, "de", source="extraction", provider="embedded")
    assert real_sidecar_languages(str(video), {"de"}) == {"de"}


def test_a_forced_sidecar_is_not_a_main_track(app_ctx, tmp_path):
    video = _setup(tmp_path, name="Show - S01E01.de.forced.srt")
    _record(video, "de", source="provider")
    assert real_sidecar_languages(str(video), {"de"}) == set()


def test_extraction_writes_a_history_record(app_ctx, tmp_path, monkeypatch):
    """Without it, extracted sidecars could never count under policy B."""
    import services.embedded_extractor as ex

    recorded = []
    monkeypatch.setattr(
        "db.providers.record_subtitle_download", lambda *a, **kw: recorded.append((a, kw))
    )
    ex._record_extraction(str(tmp_path / "Show - S01E01.mkv"), "de", "srt")
    assert recorded and recorded[0][1].get("source") == "extraction"
