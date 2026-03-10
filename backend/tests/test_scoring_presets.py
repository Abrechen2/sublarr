"""Tests for scoring preset endpoints and validation."""

import json
import os

import pytest


@pytest.fixture(autouse=True)
def set_media_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()
    yield
    reload_settings()


class TestPresetValidation:
    def test_valid_episode_preset(self):
        from scoring_presets import validate_preset

        preset = {
            "name": "Test",
            "description": "Test preset",
            "type": "episode",
            "weights": {"episode": {"hash": 359, "series": 180}},
            "provider_modifiers": {},
        }
        assert validate_preset(preset) is True

    def test_valid_movie_preset(self):
        from scoring_presets import validate_preset

        preset = {
            "name": "Movies",
            "weights": {"movie": {"hash": 119, "title": 60}},
            "provider_modifiers": {"opensubtitles": 10},
        }
        assert validate_preset(preset) is True

    def test_valid_both_preset(self):
        from scoring_presets import validate_preset

        preset = {
            "name": "Both",
            "weights": {
                "episode": {"hash": 359},
                "movie": {"hash": 119},
            },
            "provider_modifiers": {},
        }
        assert validate_preset(preset) is True

    def test_missing_name_invalid(self):
        from scoring_presets import validate_preset

        assert validate_preset({"weights": {}}) is False

    def test_invalid_weight_key(self):
        from scoring_presets import validate_preset

        preset = {
            "name": "Bad",
            "weights": {"episode": {"nonexistent_key": 999}},
            "provider_modifiers": {},
        }
        assert validate_preset(preset) is False

    def test_invalid_score_type(self):
        from scoring_presets import validate_preset

        preset = {
            "name": "Bad",
            "weights": {"special": {"hash": 359}},
            "provider_modifiers": {},
        }
        assert validate_preset(preset) is False

    def test_empty_weights_valid(self):
        from scoring_presets import validate_preset

        assert validate_preset({"name": "Empty", "weights": {}, "provider_modifiers": {}}) is True

    def test_not_dict_invalid(self):
        from scoring_presets import validate_preset

        assert validate_preset([]) is False
        assert validate_preset("string") is False
        assert validate_preset(None) is False


class TestBundledPresets:
    def test_load_bundled_presets_returns_list(self):
        from scoring_presets import load_bundled_presets

        presets = load_bundled_presets()
        assert isinstance(presets, list)
        assert len(presets) >= 3  # anime, movies, tv

    def test_bundled_preset_names(self):
        from scoring_presets import load_bundled_presets

        names = {p["name"] for p in load_bundled_presets()}
        assert "Anime" in names
        assert "Movies" in names
        assert "TV" in names

    def test_get_bundled_preset_anime(self):
        from scoring_presets import get_bundled_preset

        preset = get_bundled_preset("Anime")
        assert preset is not None
        assert preset["name"] == "Anime"
        assert "episode" in preset["weights"]

    def test_get_bundled_preset_not_found(self):
        from scoring_presets import get_bundled_preset

        assert get_bundled_preset("DoesNotExist") is None


class TestPresetEndpoints:
    def test_list_presets(self, client):
        resp = client.get("/api/v1/scoring/presets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        names = [p["name"] for p in data]
        assert "Anime" in names

    def test_get_preset_by_name(self, client):
        resp = client.get("/api/v1/scoring/presets/Anime")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Anime"
        assert "weights" in data

    def test_get_preset_not_found(self, client):
        resp = client.get("/api/v1/scoring/presets/DoesNotExist")
        assert resp.status_code == 404

    def test_import_preset(self, client):
        preset = {
            "name": "TestImport",
            "weights": {"episode": {"hash": 400, "series": 200}},
            "provider_modifiers": {"opensubtitles": 15},
        }
        resp = client.post(
            "/api/v1/scoring/presets/import",
            json=preset,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["preset"] == "TestImport"

    def test_import_invalid_preset(self, client):
        resp = client.post(
            "/api/v1/scoring/presets/import",
            json={"bad": "data"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_import_preset_updates_weights(self, client):
        """Import applies weights to the DB and invalidates cache."""
        preset = {
            "name": "CacheTest",
            "weights": {"episode": {"hash": 500}},
            "provider_modifiers": {},
        }
        resp = client.post("/api/v1/scoring/presets/import", json=preset)
        assert resp.status_code == 200

        # Verify weights are stored
        weights_resp = client.get("/api/v1/scoring/weights")
        assert weights_resp.status_code == 200
        weights = weights_resp.get_json()
        assert weights["episode"]["hash"] == 500
