"""HTTP tests for routes/providers.py — list, test, search, stats, enable, cache."""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# GET /api/v1/providers — list providers
# ---------------------------------------------------------------------------


def test_list_providers_returns_list(client, mock_provider_manager):
    mock_provider_manager.get_provider_status.return_value = [
        {"name": "animetosho", "healthy": True, "enabled": True, "initialized": True, "stats": {}},
    ]
    resp = client.get("/api/v1/providers")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "providers" in data
    assert isinstance(data["providers"], list)


def test_list_providers_empty(client, mock_provider_manager):
    mock_provider_manager.get_provider_status.return_value = []
    resp = client.get("/api/v1/providers")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["providers"] == []


def test_list_providers_multiple(client, mock_provider_manager):
    mock_provider_manager.get_provider_status.return_value = [
        {"name": "animetosho", "healthy": True, "enabled": True, "initialized": True, "stats": {}},
        {"name": "opensubtitles", "healthy": False, "enabled": False, "initialized": False, "stats": {}},
    ]
    resp = client.get("/api/v1/providers")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["providers"]) == 2


# ---------------------------------------------------------------------------
# POST /api/v1/providers/test/<provider_name> — test provider
# ---------------------------------------------------------------------------


def test_test_provider_not_found(client, mock_provider_manager):
    mock_provider_manager._providers = {}
    resp = client.post("/api/v1/providers/test/nonexistent")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_test_provider_health_ok(client, mock_provider_manager):
    mock_prov = MagicMock()
    mock_prov.health_check.return_value = (True, "OK")
    mock_prov.session = MagicMock()
    mock_provider_manager._providers = {"animetosho": mock_prov}

    resp = client.post("/api/v1/providers/test/animetosho", json={})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["provider"] == "animetosho"
    assert data["health_check"]["healthy"] is True
    assert data["health_check"]["message"] == "OK"


def test_test_provider_health_fail(client, mock_provider_manager):
    mock_prov = MagicMock()
    mock_prov.health_check.return_value = (False, "Connection refused")
    mock_prov.session = None
    mock_provider_manager._providers = {"opensubtitles": mock_prov}

    resp = client.post("/api/v1/providers/test/opensubtitles", json={})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["health_check"]["healthy"] is False


def test_test_provider_health_raises(client, mock_provider_manager):
    mock_prov = MagicMock()
    mock_prov.health_check.side_effect = RuntimeError("timeout")
    mock_prov.session = None
    mock_provider_manager._providers = {"failing_prov": mock_prov}

    resp = client.post("/api/v1/providers/test/failing_prov", json={})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["health_check"]["healthy"] is False
    assert "timeout" in data["health_check"]["message"]


def test_test_provider_with_search(client, mock_provider_manager):
    from providers.base import SubtitleFormat, SubtitleResult

    mock_result = MagicMock()
    mock_result.filename = "test.de.srt"
    mock_result.language = "de"
    mock_result.format = SubtitleFormat.SRT
    mock_result.score = 80

    mock_prov = MagicMock()
    mock_prov.health_check.return_value = (True, "OK")
    mock_prov.session = MagicMock()
    mock_prov.search.return_value = [mock_result]
    mock_provider_manager._providers = {"animetosho": mock_prov}

    resp = client.post(
        "/api/v1/providers/test/animetosho",
        json={
            "test_search": True,
            "query": {"series_title": "Test Show", "season": 1, "episode": 1, "language": "de"},
        },
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert "search_test" in data
    assert data["search_test"]["success"] is True
    assert data["search_test"]["results_count"] == 1


# ---------------------------------------------------------------------------
# POST /api/v1/providers/search — search providers
# ---------------------------------------------------------------------------


def test_search_providers_returns_results(client, mock_provider_manager):
    from providers.base import SubtitleFormat

    mock_result = MagicMock()
    mock_result.provider_name = "animetosho"
    mock_result.subtitle_id = "abc123"
    mock_result.language = "de"
    mock_result.format = SubtitleFormat.SRT
    mock_result.filename = "show.de.srt"
    mock_result.release_info = "720p"
    mock_result.score = 90
    mock_result.score_breakdown = {}
    mock_result.hearing_impaired = False
    mock_result.matches = set()

    mock_provider_manager.search.return_value = [mock_result]

    resp = client.post(
        "/api/v1/providers/search",
        json={
            "series_title": "Test Show",
            "season": 1,
            "episode": 1,
            "language": "de",
        },
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert "results" in data
    assert data["total"] == 1
    assert data["results"][0]["provider"] == "animetosho"


def test_search_providers_empty_results(client, mock_provider_manager):
    mock_provider_manager.search.return_value = []
    resp = client.post("/api/v1/providers/search", json={"series_title": "Unknown Show"})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["results"] == []
    assert data["total"] == 0


def test_search_providers_with_format_filter(client, mock_provider_manager):
    mock_provider_manager.search.return_value = []
    resp = client.post(
        "/api/v1/providers/search",
        json={"series_title": "Show", "format": "ass"},
    )
    assert resp.status_code == 200


def test_search_providers_invalid_format_ignored(client, mock_provider_manager):
    # Invalid format should be silently ignored (contextlib.suppress)
    mock_provider_manager.search.return_value = []
    resp = client.post(
        "/api/v1/providers/search",
        json={"series_title": "Show", "format": "invalid_fmt"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/providers/stats — provider statistics
# ---------------------------------------------------------------------------


def test_provider_stats_returns_structure(client, mock_provider_manager):
    with (
        patch("db.providers.get_provider_cache_stats", return_value={"hits": 10, "misses": 5}),
        patch("db.providers.get_provider_download_stats", return_value={"animetosho": 3}),
        patch("db.providers.get_all_provider_stats_enriched", return_value=[]),
    ):
        resp = client.get("/api/v1/providers/stats")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "cache" in data
    assert "downloads" in data
    assert "performance" in data


# ---------------------------------------------------------------------------
# GET /api/v1/providers/health — provider health overview
# ---------------------------------------------------------------------------


def test_provider_health_returns_list(client, mock_provider_manager):
    mock_provider_manager.get_provider_status.return_value = [
        {
            "name": "animetosho",
            "healthy": True,
            "enabled": True,
            "initialized": True,
            "stats": {
                "success_rate": 0.95,
                "avg_response_time_ms": 200,
                "last_response_time_ms": 150,
                "auto_disabled": False,
                "disabled_until": "",
                "consecutive_failures": 0,
                "total_searches": 50,
            },
        }
    ]
    resp = client.get("/api/v1/providers/health")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "providers" in data
    assert len(data["providers"]) == 1
    assert data["providers"][0]["name"] == "animetosho"
    assert "success_rate" in data["providers"][0]


# ---------------------------------------------------------------------------
# POST /api/v1/providers/<name>/enable — re-enable provider
# ---------------------------------------------------------------------------


def test_enable_provider_not_disabled(client):
    with patch("db.providers.is_provider_auto_disabled", return_value=False):
        resp = client.post("/api/v1/providers/animetosho/enable")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "already_enabled"


def test_enable_provider_was_disabled(client):
    with (
        patch("db.providers.is_provider_auto_disabled", return_value=True),
        patch("db.providers.clear_auto_disable") as mock_clear,
    ):
        resp = client.post("/api/v1/providers/animetosho/enable")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "enabled"
    mock_clear.assert_called_once_with("animetosho")


# ---------------------------------------------------------------------------
# POST /api/v1/providers/cache/clear — clear provider cache
# ---------------------------------------------------------------------------


def test_clear_cache_all(client):
    with patch("db.providers.clear_provider_cache") as mock_clear:
        resp = client.post("/api/v1/providers/cache/clear", json={})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "cleared"
    assert data["provider"] == "all"
    mock_clear.assert_called_once_with(None)


def test_clear_cache_specific_provider(client):
    with patch("db.providers.clear_provider_cache") as mock_clear:
        resp = client.post(
            "/api/v1/providers/cache/clear", json={"provider_name": "animetosho"}
        )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["provider"] == "animetosho"
    mock_clear.assert_called_once_with("animetosho")
