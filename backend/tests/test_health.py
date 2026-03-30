"""Tests for health check endpoints."""

import pytest


def test_health_returns_503_when_ollama_down(client, mocker):
    """GET /health must return 503 when Ollama reports unhealthy."""
    mocker.patch(
        "routes.system.health._health_check_ollama",
        return_value=({"ollama": "unreachable"}, False),
    )
    mocker.patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    mocker.patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "ok"}, None),
    )
    mocker.patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "ok"}, None),
    )
    mocker.patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "1/1 healthy"}, None),
    )
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.json["status"] == "unhealthy"


def test_health_returns_200_when_ollama_healthy(client, mocker):
    """GET /health must return 200 when Ollama is healthy."""
    mocker.patch(
        "routes.system.health._health_check_ollama",
        return_value=({"ollama": "ok"}, True),
    )
    mocker.patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    mocker.patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "ok"}, None),
    )
    mocker.patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "ok"}, None),
    )
    mocker.patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "1/1 healthy"}, None),
    )
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "healthy"
