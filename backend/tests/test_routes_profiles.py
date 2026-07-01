"""Tests for routes/profiles.py — language profile CRUD and assignment endpoints."""

from unittest.mock import MagicMock, patch

import pytest

SAMPLE_PROFILE = {
    "id": 1,
    "name": "My Profile",
    "source_language": "en",
    "source_language_name": "English",
    "target_languages": ["de"],
    "target_language_names": ["German"],
    "translation_backend": "ollama",
    "fallback_chain": None,
    "forced_preference": "disabled",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_cache(monkeypatch):
    """Patch invalidate_response_cache so tests don't touch real cache."""
    monkeypatch.setattr("cache_response.invalidate_response_cache", lambda: None)


# ---------------------------------------------------------------------------
# TestListLanguageProfiles — GET /api/v1/language-profiles
# ---------------------------------------------------------------------------


class TestListLanguageProfiles:
    """Tests for GET /api/v1/language-profiles."""

    def test_returns_profiles_list_with_profiles_key(self, client):
        with (
            patch("db.profiles.get_all_language_profiles", return_value=[SAMPLE_PROFILE]),
            patch("cache_response.cached_get", lambda **kw: lambda f: f),
        ):
            resp = client.get("/api/v1/language-profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "profiles" in data
        assert len(data["profiles"]) == 1
        assert data["profiles"][0]["name"] == "My Profile"

    def test_returns_empty_list_when_no_profiles(self, client):
        with (
            patch("db.profiles.get_all_language_profiles", return_value=[]),
            patch("cache_response.cached_get", lambda **kw: lambda f: f),
        ):
            resp = client.get("/api/v1/language-profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profiles"] == []


# ---------------------------------------------------------------------------
# TestCreateLanguageProfile — POST /api/v1/language-profiles
# ---------------------------------------------------------------------------


class TestCreateLanguageProfile:
    """Tests for POST /api/v1/language-profiles."""

    def test_400_when_name_missing(self, client):
        resp = client.post(
            "/api/v1/language-profiles",
            json={"target_languages": ["de"]},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "name" in data["error"].lower()

    def test_400_when_target_languages_empty(self, client):
        resp = client.post(
            "/api/v1/language-profiles",
            json={"name": "Test", "target_languages": []},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "target language" in data["error"].lower()

    def test_400_for_invalid_forced_preference(self, client):
        resp = client.post(
            "/api/v1/language-profiles",
            json={
                "name": "Test",
                "target_languages": ["de"],
                "forced_preference": "invalid_value",
            },
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "forced_preference" in data["error"]

    def test_409_on_duplicate_name(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        with patch(
            "db.profiles.create_language_profile",
            side_effect=Exception("UNIQUE constraint failed"),
        ):
            resp = client.post(
                "/api/v1/language-profiles",
                json={"name": "My Profile", "target_languages": ["de"]},
            )
        assert resp.status_code == 409
        data = resp.get_json()
        assert "already exists" in data["error"]

    def test_201_on_success_with_profile_data(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        with (
            patch("db.profiles.create_language_profile", return_value=1),
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
        ):
            resp = client.post(
                "/api/v1/language-profiles",
                json={"name": "My Profile", "target_languages": ["de"]},
            )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["id"] == 1
        assert data["name"] == "My Profile"


# ---------------------------------------------------------------------------
# TestUpdateLanguageProfile — PUT /api/v1/language-profiles/<id>
# ---------------------------------------------------------------------------


class TestUpdateLanguageProfile:
    """Tests for PUT /api/v1/language-profiles/<id>."""

    def test_404_for_unknown_id(self, client):
        with patch("db.profiles.get_language_profile", return_value=None):
            resp = client.put("/api/v1/language-profiles/999", json={"name": "New Name"})
        assert resp.status_code == 404
        data = resp.get_json()
        assert "not found" in data["error"].lower()

    def test_400_when_no_updatable_fields(self, client):
        with patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE):
            resp = client.put("/api/v1/language-profiles/1", json={"unknown_field": "value"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "no fields" in data["error"].lower()

    def test_400_for_invalid_forced_preference(self, client):
        with patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE):
            resp = client.put(
                "/api/v1/language-profiles/1",
                json={"forced_preference": "bad_value"},
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "forced_preference" in data["error"]

    def test_200_on_success_returns_updated_profile(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        updated = {**SAMPLE_PROFILE, "name": "Renamed Profile"}
        with (
            patch("db.profiles.get_language_profile", side_effect=[SAMPLE_PROFILE, updated]),
            patch("db.profiles.update_language_profile"),
        ):
            resp = client.put("/api/v1/language-profiles/1", json={"name": "Renamed Profile"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Renamed Profile"

    def test_409_on_duplicate_name(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        with (
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
            patch(
                "db.profiles.update_language_profile",
                side_effect=Exception("UNIQUE constraint failed"),
            ),
        ):
            resp = client.put("/api/v1/language-profiles/1", json={"name": "Existing Name"})
        assert resp.status_code == 409
        data = resp.get_json()
        assert "already exists" in data["error"]

    def test_translation_backend_and_fallback_chain_round_trip(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        updated = {
            **SAMPLE_PROFILE,
            "translation_backend": "deepl",
            "fallback_chain": ["deepl", "ollama"],
        }
        with (
            patch("db.profiles.get_language_profile", side_effect=[SAMPLE_PROFILE, updated]),
            patch("db.profiles.update_language_profile") as mock_update,
        ):
            resp = client.put(
                "/api/v1/language-profiles/1",
                json={"translation_backend": "deepl", "fallback_chain": ["deepl", "ollama"]},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["translation_backend"] == "deepl"
        assert data["fallback_chain"] == ["deepl", "ollama"]
        mock_update.assert_called_once_with(
            1, translation_backend="deepl", fallback_chain=["deepl", "ollama"]
        )

    def test_translation_backend_and_fallback_chain_clear_to_inherit(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        updated = {**SAMPLE_PROFILE, "translation_backend": "", "fallback_chain": []}
        with (
            patch("db.profiles.get_language_profile", side_effect=[SAMPLE_PROFILE, updated]),
            patch("db.profiles.update_language_profile") as mock_update,
        ):
            resp = client.put(
                "/api/v1/language-profiles/1",
                json={"translation_backend": "", "fallback_chain": []},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["translation_backend"] == ""
        assert data["fallback_chain"] == []
        mock_update.assert_called_once_with(1, translation_backend="", fallback_chain=[])


# ---------------------------------------------------------------------------
# TestDeleteLanguageProfile — DELETE /api/v1/language-profiles/<id>
# ---------------------------------------------------------------------------


class TestDeleteLanguageProfile:
    """Tests for DELETE /api/v1/language-profiles/<id>."""

    def test_400_when_delete_returns_false(self, client):
        with patch("db.profiles.delete_language_profile", return_value=False):
            resp = client.delete("/api/v1/language-profiles/1")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "not found" in data["error"].lower() or "default" in data["error"].lower()

    def test_200_on_success_with_status_and_id(self, client, monkeypatch):
        _patch_cache(monkeypatch)
        with patch("db.profiles.delete_language_profile", return_value=True):
            resp = client.delete("/api/v1/language-profiles/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "deleted"
        assert data["id"] == 1


# ---------------------------------------------------------------------------
# TestAssignProfile — PUT /api/v1/language-profiles/assign
# ---------------------------------------------------------------------------


class TestAssignProfile:
    """Tests for PUT /api/v1/language-profiles/assign."""

    def test_400_missing_type(self, client):
        resp = client.put(
            "/api/v1/language-profiles/assign",
            json={"arr_id": 10, "profile_id": 1},
        )
        assert resp.status_code == 400

    def test_400_missing_arr_id(self, client):
        resp = client.put(
            "/api/v1/language-profiles/assign",
            json={"type": "series", "profile_id": 1},
        )
        assert resp.status_code == 400

    def test_400_invalid_type_value(self, client):
        with patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE):
            resp = client.put(
                "/api/v1/language-profiles/assign",
                json={"type": "episode", "arr_id": 10, "profile_id": 1},
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "type" in data["error"].lower()

    def test_200_series_assignment_calls_correct_function(self, client):
        mock_assign = MagicMock()
        with (
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
            patch("db.profiles.assign_series_profile", mock_assign),
        ):
            resp = client.put(
                "/api/v1/language-profiles/assign",
                json={"type": "series", "arr_id": 42, "profile_id": 1},
            )
        assert resp.status_code == 200
        mock_assign.assert_called_once_with(42, 1)
        data = resp.get_json()
        assert data["status"] == "assigned"
        assert data["type"] == "series"
        assert data["arr_id"] == 42

    def test_200_movie_assignment_calls_correct_function(self, client):
        mock_assign = MagicMock()
        with (
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
            patch("db.profiles.assign_movie_profile", mock_assign),
        ):
            resp = client.put(
                "/api/v1/language-profiles/assign",
                json={"type": "movie", "arr_id": 99, "profile_id": 1},
            )
        assert resp.status_code == 200
        mock_assign.assert_called_once_with(99, 1)
        data = resp.get_json()
        assert data["status"] == "assigned"
        assert data["type"] == "movie"
        assert data["arr_id"] == 99

    def test_404_when_profile_not_found(self, client):
        with patch("db.profiles.get_language_profile", return_value=None):
            resp = client.put(
                "/api/v1/language-profiles/assign",
                json={"type": "series", "arr_id": 10, "profile_id": 999},
            )
        assert resp.status_code == 404
        data = resp.get_json()
        assert "not found" in data["error"].lower()


# ---------------------------------------------------------------------------
# TestAssignProfileBulk — PUT /api/v1/language-profiles/assign-bulk
# ---------------------------------------------------------------------------


class TestAssignProfileBulk:
    """Tests for PUT /api/v1/language-profiles/assign-bulk."""

    def test_assigns_all_when_profile_exists(self, client):
        mock_assign_series = MagicMock()
        with (
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
            patch("db.profiles.assign_series_profile", mock_assign_series),
        ):
            resp = client.put(
                "/api/v1/language-profiles/assign-bulk",
                json={"type": "series", "arr_ids": [10, 20, 30], "profile_id": 1},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["assigned"] == 3
        assert data["failed"] == []
        assert mock_assign_series.call_count == 3

    def test_partial_failure_when_profile_not_found(self, client):
        with patch("db.profiles.get_language_profile", return_value=None):
            resp = client.put(
                "/api/v1/language-profiles/assign-bulk",
                json={"type": "series", "arr_ids": [10, 20], "profile_id": 99999},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["assigned"] == 0
        assert len(data["failed"]) == 2

    def test_400_on_missing_required_fields(self, client):
        resp = client.put(
            "/api/v1/language-profiles/assign-bulk",
            json={"type": "series"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
