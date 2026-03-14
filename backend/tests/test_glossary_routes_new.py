"""Tests for new glossary endpoints: POST /series/<id>/glossary/suggest and GET /glossary/export."""

import json
from unittest.mock import MagicMock

# ─── Suggest endpoint ─────────────────────────────────────────────────────────


def test_suggest_returns_candidates(client, monkeypatch):
    """POST /series/<id>/glossary/suggest returns extracted candidates from glossary_extractor."""
    fake_candidates = [
        {"source_term": "Naruto", "term_type": "character", "frequency": 42, "confidence": 0.92},
        {"source_term": "Konoha", "term_type": "place", "frequency": 17, "confidence": 0.67},
    ]

    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = {"id": 1, "path": "/media/naruto"}
    monkeypatch.setattr("routes.library.get_sonarr_client", lambda: mock_sonarr)

    monkeypatch.setattr(
        "routes.library.extract_candidates",
        lambda directory, source_lang, min_freq, max_candidates: fake_candidates,
    )

    resp = client.post(
        "/api/v1/series/1/glossary/suggest",
        data=json.dumps({"source_lang": "en", "min_freq": 2}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["series_id"] == 1
    assert data["candidates"] == fake_candidates


def test_suggest_series_not_found(client, monkeypatch):
    """POST /series/<id>/glossary/suggest returns empty candidates when series not in Sonarr."""
    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = None
    monkeypatch.setattr("routes.library.get_sonarr_client", lambda: mock_sonarr)

    resp = client.post(
        "/api/v1/series/999/glossary/suggest",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidates"] == []
    assert "message" in data


def test_suggest_sonarr_not_configured(client, monkeypatch):
    """POST /series/<id>/glossary/suggest returns empty candidates when Sonarr not configured."""
    monkeypatch.setattr("routes.library.get_sonarr_client", lambda: None)

    resp = client.post(
        "/api/v1/series/1/glossary/suggest",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidates"] == []
    assert "message" in data


def test_suggest_uses_defaults_when_no_body(client, monkeypatch):
    """POST /series/<id>/glossary/suggest uses source_lang='en' and min_freq=3 by default."""
    captured = {}

    def fake_extract(directory, source_lang, min_freq, max_candidates):
        captured["source_lang"] = source_lang
        captured["min_freq"] = min_freq
        return []

    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = {"id": 1, "path": "/media/test"}
    monkeypatch.setattr("routes.library.get_sonarr_client", lambda: mock_sonarr)
    monkeypatch.setattr("routes.library.extract_candidates", fake_extract)

    resp = client.post(
        "/api/v1/series/1/glossary/suggest",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert captured["source_lang"] == "en"
    assert captured["min_freq"] == 3


# ─── Export endpoint ───────────────────────────────────────────────────────────


def test_export_tsv_has_header(client):
    """GET /glossary/export returns a TSV with a header row as first line."""
    resp = client.get("/api/v1/glossary/export")

    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    first_line = text.splitlines()[0]
    assert first_line == "source_term\ttarget_term\tterm_type\tnotes"


def test_export_tsv_content_type(client):
    """GET /glossary/export sets Content-Type to text/tab-separated-values; charset=utf-8."""
    resp = client.get("/api/v1/glossary/export")

    assert resp.status_code == 200
    assert "text/tab-separated-values" in resp.content_type
    assert "utf-8" in resp.content_type


def test_export_tsv_filename_global(client):
    """GET /glossary/export (no series_id) uses filename glossary_global.tsv."""
    resp = client.get("/api/v1/glossary/export")

    assert resp.status_code == 200
    disposition = resp.headers.get("Content-Disposition", "")
    assert "glossary_global.tsv" in disposition


def test_export_tsv_series_scoped(client):
    """GET /glossary/export?series_id=5 uses filename glossary_series_5.tsv."""
    resp = client.get("/api/v1/glossary/export?series_id=5")

    assert resp.status_code == 200
    disposition = resp.headers.get("Content-Disposition", "")
    assert "glossary_series_5.tsv" in disposition


def test_export_tsv_content(client):
    """GET /glossary/export includes glossary entries as TSV rows after the header."""
    from db.translation import add_glossary_entry

    add_glossary_entry(None, "Naruto", "Naruto", "")
    add_glossary_entry(None, "Konoha", "Konoha", "leaf village")

    resp = client.get("/api/v1/glossary/export")

    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    lines = text.splitlines()
    # Header + at least 2 data rows
    assert len(lines) >= 3
    # Each non-header line must have exactly 3 tabs (4 columns)
    for line in lines[1:]:
        assert line.count("\t") == 3


def test_export_tsv_notes_tabs_replaced(client):
    """GET /glossary/export replaces tabs in notes with spaces."""
    from db.translation import add_glossary_entry

    add_glossary_entry(None, "Term", "Term", "note\twith\ttabs")

    resp = client.get("/api/v1/glossary/export")

    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    # Notes column should not contain literal tabs (they'd be replaced by spaces)
    lines = text.splitlines()
    data_lines = [l for l in lines[1:] if l.startswith("Term\t")]
    assert len(data_lines) == 1
    # Split on tab — 4 columns exactly
    cols = data_lines[0].split("\t")
    assert len(cols) == 4
    # Notes column (index 3) has no remaining tabs
    assert "\t" not in cols[3]
