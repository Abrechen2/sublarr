"""Tests for /api/v1/series/<series_id>/audio-track-pref routes."""

import pytest


class TestGetAudioPref:
    def test_get_audio_pref_defaults_to_null(self, client):
        resp = client.get("/api/v1/series/1/audio-track-pref")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["series_id"] == 1
        assert data["preferred_audio_track_index"] is None

    def test_get_audio_pref_reflects_set(self, client):
        client.put(
            "/api/v1/series/5/audio-track-pref",
            json={"preferred_audio_track_index": 3},
        )
        resp = client.get("/api/v1/series/5/audio-track-pref")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preferred_audio_track_index"] == 3


class TestSetAudioPref:
    def test_set_audio_pref_valid(self, client):
        resp = client.put(
            "/api/v1/series/1/audio-track-pref",
            json={"preferred_audio_track_index": 2},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preferred_audio_track_index"] == 2

    def test_set_audio_pref_null_clears(self, client):
        client.put(
            "/api/v1/series/1/audio-track-pref",
            json={"preferred_audio_track_index": 1},
        )
        resp = client.put(
            "/api/v1/series/1/audio-track-pref",
            json={"preferred_audio_track_index": None},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preferred_audio_track_index"] is None

    def test_set_audio_pref_missing_field(self, client):
        resp = client.put(
            "/api/v1/series/1/audio-track-pref",
            json={},
        )
        assert resp.status_code == 400

    def test_set_audio_pref_negative_rejected(self, client):
        resp = client.put(
            "/api/v1/series/1/audio-track-pref",
            json={"preferred_audio_track_index": -1},
        )
        assert resp.status_code == 400
