"""Tests for per-series audio track preference."""

import pytest


class TestSeriesAudioPrefModel:
    def test_series_settings_has_audio_track_field(self):
        from db.models.core import SeriesSettings

        ss = SeriesSettings(sonarr_series_id=1, absolute_order=0, updated_at="2026-01-01")
        assert hasattr(ss, "preferred_audio_track_index")
        assert ss.preferred_audio_track_index is None


class TestGetAudioTrackByIndex:
    def test_valid_index_returns_track_dict(self, monkeypatch):
        from whisper.audio import get_audio_track_by_index

        fake = [
            {"stream_index": 0, "language": "jpn", "codec": "aac", "channels": 2, "title": ""},
            {"stream_index": 1, "language": "eng", "codec": "aac", "channels": 2, "title": ""},
        ]
        monkeypatch.setattr("whisper.audio.get_audio_streams", lambda _: fake)
        track = get_audio_track_by_index("/fake/file.mkv", 1)
        assert track["stream_index"] == 1
        assert track["language"] == "eng"

    def test_out_of_range_raises(self, monkeypatch):
        from whisper.audio import get_audio_track_by_index

        monkeypatch.setattr(
            "whisper.audio.get_audio_streams",
            lambda _: [{"stream_index": 0, "language": "jpn", "codec": "aac", "channels": 2, "title": ""}],
        )
        with pytest.raises(ValueError, match="out of range"):
            get_audio_track_by_index("/fake/file.mkv", 5)


class TestSeriesAudioRepository:
    def test_get_returns_none_for_unknown_series(self, app_ctx):
        from db.repositories.series_audio import SeriesAudioRepository

        result = SeriesAudioRepository().get_audio_track_pref(series_id=9999)
        assert result is None

    def test_set_and_get_roundtrip(self, app_ctx):
        from db.repositories.series_audio import SeriesAudioRepository

        repo = SeriesAudioRepository()
        repo.set_audio_track_pref(series_id=42, track_index=2)
        assert repo.get_audio_track_pref(series_id=42) == 2

    def test_set_to_none_clears(self, app_ctx):
        from db.repositories.series_audio import SeriesAudioRepository

        repo = SeriesAudioRepository()
        repo.set_audio_track_pref(series_id=42, track_index=1)
        repo.set_audio_track_pref(series_id=42, track_index=None)
        assert repo.get_audio_track_pref(series_id=42) is None


class TestSeriesAudioPrefRoutes:
    def test_get_unknown_returns_null(self, client):
        r = client.get("/api/v1/series/9999/audio-track-pref")
        assert r.status_code == 200
        d = r.get_json()
        assert d["series_id"] == 9999
        assert d["preferred_audio_track_index"] is None

    def test_put_sets_preference(self, client):
        r = client.put(
            "/api/v1/series/42/audio-track-pref",
            json={"preferred_audio_track_index": 1},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["preferred_audio_track_index"] == 1

    def test_get_reflects_put(self, client):
        client.put(
            "/api/v1/series/43/audio-track-pref",
            json={"preferred_audio_track_index": 3},
            content_type="application/json",
        )
        assert (
            client.get("/api/v1/series/43/audio-track-pref").get_json()[
                "preferred_audio_track_index"
            ]
            == 3
        )

    def test_put_null_clears(self, client):
        client.put(
            "/api/v1/series/44/audio-track-pref",
            json={"preferred_audio_track_index": 2},
            content_type="application/json",
        )
        client.put(
            "/api/v1/series/44/audio-track-pref",
            json={"preferred_audio_track_index": None},
            content_type="application/json",
        )
        assert (
            client.get("/api/v1/series/44/audio-track-pref").get_json()[
                "preferred_audio_track_index"
            ]
            is None
        )

    def test_put_negative_rejected(self, client):
        r = client.put(
            "/api/v1/series/45/audio-track-pref",
            json={"preferred_audio_track_index": -1},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_put_string_rejected(self, client):
        r = client.put(
            "/api/v1/series/45/audio-track-pref",
            json={"preferred_audio_track_index": "auto"},
            content_type="application/json",
        )
        assert r.status_code == 400
