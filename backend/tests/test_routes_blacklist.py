"""Tests for /api/v1/blacklist routes."""

import pytest


class TestListBlacklist:
    def test_list_blacklist_empty(self, client):
        resp = client.get("/api/v1/blacklist")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["data"] == []


class TestAddBlacklist:
    def test_add_blacklist_entry(self, client):
        resp = client.post(
            "/api/v1/blacklist",
            json={"provider_name": "opensubtitles", "subtitle_id": "abc123"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "added"
        assert isinstance(data["id"], int)

    def test_add_blacklist_missing_fields(self, client):
        resp = client.post(
            "/api/v1/blacklist",
            json={"provider_name": "opensubtitles"},
        )
        assert resp.status_code == 400


class TestDeleteBlacklist:
    def test_delete_blacklist_entry(self, client):
        add_resp = client.post(
            "/api/v1/blacklist",
            json={"provider_name": "opensubtitles", "subtitle_id": "del_me"},
        )
        entry_id = add_resp.get_json()["id"]

        del_resp = client.delete(f"/api/v1/blacklist/{entry_id}")
        assert del_resp.status_code == 200
        data = del_resp.get_json()
        assert data["status"] == "deleted"

    def test_delete_blacklist_entry_not_found(self, client):
        resp = client.delete("/api/v1/blacklist/99999")
        assert resp.status_code == 404


class TestClearBlacklist:
    def test_clear_blacklist_requires_confirm(self, client):
        resp = client.delete("/api/v1/blacklist")
        assert resp.status_code == 400

    def test_clear_blacklist_with_confirm(self, client):
        client.post(
            "/api/v1/blacklist",
            json={"provider_name": "opensubtitles", "subtitle_id": "to_clear"},
        )
        resp = client.delete("/api/v1/blacklist?confirm=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "cleared"


class TestBlacklistCount:
    def test_blacklist_count(self, client):
        resp = client.get("/api/v1/blacklist/count")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "count" in data


class TestAddBlacklistFileHashValidation:
    """Audit 2026-04-30: file_hash is VARCHAR(64) and must be validated at
    the route boundary. Without this, a PostgreSQL deployment 500s on
    oversized values; SQLite silently stores them and breaks the partial
    UNIQUE index assumption."""

    def test_oversized_file_hash_returns_400(self, client):
        resp = client.post(
            "/api/v1/blacklist",
            json={
                "provider_name": "opensubtitles",
                "subtitle_id": "abc",
                "file_hash": "a" * 65,  # 65 chars — one over the column limit
            },
        )
        assert resp.status_code == 400
        assert "file_hash" in resp.get_json()["error"]

    def test_non_string_file_hash_returns_400(self, client):
        resp = client.post(
            "/api/v1/blacklist",
            json={
                "provider_name": "opensubtitles",
                "subtitle_id": "abc",
                "file_hash": 12345,
            },
        )
        assert resp.status_code == 400

    def test_exactly_64_char_file_hash_is_accepted(self, client):
        resp = client.post(
            "/api/v1/blacklist",
            json={
                "provider_name": "opensubtitles",
                "subtitle_id": "exact_len",
                "file_hash": "a" * 64,
            },
        )
        assert resp.status_code == 201

    def test_omitted_file_hash_still_works(self, client):
        resp = client.post(
            "/api/v1/blacklist",
            json={"provider_name": "opensubtitles", "subtitle_id": "no_hash"},
        )
        assert resp.status_code == 201
