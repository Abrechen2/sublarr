"""Tests for POST /api/v1/standalone/series/{id}/scan route."""


def test_scan_series_not_found(client):
    """Returns 404 when series does not exist."""
    resp = client.post("/api/v1/standalone/series/99999/scan")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_scan_series_ok(client, mocker):
    """Returns 200 and triggers fallback refresh when standalone manager unavailable."""
    mock_series = {
        "id": 1,
        "title": "Test Series",
        "folder_path": "/media/test",
    }
    # Patch the local import inside the route function
    mocker.patch("db.standalone.get_standalone_series", return_value=mock_series)
    # Mock db.get_db to avoid actual DB operations
    mock_db = mocker.MagicMock()
    mock_db.execute.return_value = None
    mocker.patch("db.get_db", return_value=mock_db)

    resp = client.post("/api/v1/standalone/series/1/scan")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["series_id"] == 1
    assert "message" in data
