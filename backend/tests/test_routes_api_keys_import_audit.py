"""Regression tests for the 2026-04-30 API Keys import audit.

Pins:
- /api/v1/api-keys/import — ZIP-bomb protection on member reads
  (a 16 MB upload could previously decompress into multi-GB RAM
  via a single high-ratio entry; safe_read_zip_member() now caps).
- /api/v1/api-keys/import — JSON shape validation (config.json
  must be a dict, profiles.json / glossary.json must be lists);
  previously a non-dict config.json crashed inside the for-loop.
- /api/v1/api-keys/import (CSV) — row cap (10000) so a malformed
  binary-as-CSV upload that decodes to thousands of ambiguous
  rows can't pin a worker for minutes.
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import patch

import pytest


def _zip_bytes(entries: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ZIP-bomb protection on /import
# ---------------------------------------------------------------------------


class TestImportZipBomb:
    """A high-ratio ZIP entry must be refused with 400 instead of OOMing
    the process. Pre-fix the import called ``zf.read(name)`` directly
    with no size or ratio check."""

    def test_bomb_in_config_json_returns_400(self, client):
        # 200 KB of zeros — compresses to a few hundred bytes (>>100:1).
        bomb = b"\x00" * (200 * 1024)
        zip_bytes = _zip_bytes({"config.json": bomb})

        resp = client.post(
            "/api/v1/api-keys/import",
            data={"file": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )

        assert resp.status_code == 400
        body = resp.get_json()
        assert "ZIP bomb" in body["error"] or "too large" in body["error"]

    def test_bomb_in_profiles_json_returns_400(self, client):
        bomb = b"x" * (200 * 1024)
        zip_bytes = _zip_bytes(
            {
                "config.json": b"{}",
                "profiles.json": bomb,
            }
        )

        resp = client.post(
            "/api/v1/api-keys/import",
            data={"file": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_normal_zip_still_imports(self, client):
        """The bomb guard must not break the happy path."""
        zip_bytes = _zip_bytes(
            {
                "config.json": json.dumps({"sonarr_url": "http://test:8989"}).encode(),
                "profiles.json": json.dumps([]).encode(),
                "glossary.json": json.dumps([]).encode(),
            }
        )

        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            resp = client.post(
                "/api/v1/api-keys/import",
                data={"file": (io.BytesIO(zip_bytes), "export.zip")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "imported"
        assert body["config_imported"] >= 0
        # save_config_entry should have been called for the one config key
        # (allowing for the masked-value skip path — sonarr_url has no ***).
        mock_save.assert_called()


# ---------------------------------------------------------------------------
# JSON shape validation
# ---------------------------------------------------------------------------


class TestImportZipShapeValidation:
    """Pre-fix a non-dict config.json crashed inside the import loop with
    AttributeError on .items(); now it returns 400 cleanly."""

    def test_non_dict_config_json_returns_400(self, client):
        zip_bytes = _zip_bytes(
            {
                "config.json": json.dumps(["not", "a", "dict"]).encode(),
            }
        )
        resp = client.post(
            "/api/v1/api-keys/import",
            data={"file": (io.BytesIO(zip_bytes), "export.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "JSON object" in resp.get_json()["error"]

    def test_non_list_profiles_json_logged_and_skipped(self, client):
        """profiles.json shape mismatch is non-fatal (logged + skipped) so
        a partial recovery still imports config + glossary if those are OK."""
        zip_bytes = _zip_bytes(
            {
                "config.json": b"{}",
                "profiles.json": json.dumps({"oops": "not a list"}).encode(),
                "glossary.json": json.dumps([]).encode(),
            }
        )

        with (
            patch("db.config.save_config_entry"),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            resp = client.post(
                "/api/v1/api-keys/import",
                data={"file": (io.BytesIO(zip_bytes), "export.zip")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["profiles_imported"] == 0


# ---------------------------------------------------------------------------
# CSV row cap on /import (CSV path)
# ---------------------------------------------------------------------------


class TestImportCsvRowCap:
    """A pathological CSV (e.g. a binary blob that happens to decode as
    thousands of valid 3-column rows) used to iterate without bound."""

    def test_oversized_csv_truncates_at_cap(self, client):
        # 10001 rows, each with valid shape (sublarr,api_key,VALUE_n).
        # Every save will fail validation against the registry (the key
        # is ``api_key`` not ``sublarr_api_key``-style), but the iteration
        # itself must stop at the 10000th row.
        rows = "\n".join(f"sublarr,api_key,value{i}" for i in range(10001))
        from io import BytesIO

        with (
            patch("db.config.save_config_entry"),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            resp = client.post(
                "/api/v1/api-keys/import",
                data={"file": (BytesIO(rows.encode("utf-8")), "keys.csv")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        body = resp.get_json()
        # The cap message must surface so the operator knows there's more.
        assert any("CSV truncated" in e for e in body["errors"])

    def test_csv_under_cap_imports_normally(self, client):
        rows = "sublarr,api_key,value1\nsonarr,sonarr_api_key,value2"

        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            resp = client.post(
                "/api/v1/api-keys/import",
                data={"file": (io.BytesIO(rows.encode()), "keys.csv")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["imported"] == 2
        assert body["errors"] == []
        assert mock_save.call_count == 2


# ---------------------------------------------------------------------------
# Bazarr ZIP — same bomb guard
# ---------------------------------------------------------------------------


class TestBazarrImportZipBomb:
    def test_bomb_in_bazarr_config_returns_400(self, client):
        bomb = b"\x00" * (200 * 1024)
        zip_bytes = _zip_bytes({"config/config.yaml": bomb})

        with patch("bazarr_migrator.parse_bazarr_config", return_value={}):
            resp = client.post(
                "/api/v1/api-keys/import/bazarr",
                data={"file": (io.BytesIO(zip_bytes), "bazarr.zip")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 400
        body = resp.get_json()
        assert "ZIP bomb" in body["error"] or "too large" in body["error"]
