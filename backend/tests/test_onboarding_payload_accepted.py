"""Everything the setup wizard saves is a setting the config endpoint accepts.

Discord install-help 2026-10-31: since 1.14.0 PUT /config refuses unknown keys,
and the wizard still sent ``automation_enabled`` / ``search_interval_hours`` —
every step answered "Failed to save settings", and the user's path mapping was
never stored. The payload below is what ``buildOnboardingPayload``
(frontend/src/pages/Onboarding.tsx) produces with every field filled.
"""

from unittest.mock import patch

ARR_PAYLOAD = {
    "sonarr_url": "http://192.168.10.40:8989",
    "sonarr_api_key": "0123456789abcdef0123456789abcdef",
    "radarr_url": "http://192.168.10.40:7878",
    "radarr_api_key": "0123456789abcdef0123456789abcdef",
    "path_mapping": "/data/media=/media",
    "opensubtitles_api_key": "k",
    "jimaku_api_key": "k",
    "subdl_api_key": "k",
    "ollama_url": "http://ollama:11434",
    "ollama_model": "qwen2.5:14b-instruct",
    "target_language": "de",
    "target_language_name": "German",
    "source_language": "en",
    "source_language_name": "English",
    "upgrade_enabled": "true",
    "wanted_search_interval_hours": "6",
}
STANDALONE_EXTRA = {"tmdb_api_key": "k", "tvdb_api_key": "k", "standalone_enabled": "true"}


def _public_ip(*args, **kwargs):
    return [(2, 1, 6, "", ("192.168.10.40", 0))]


def test_the_wizard_payload_is_saved(client):
    with patch("socket.getaddrinfo", side_effect=_public_ip):
        response = client.put("/api/v1/config", json={**ARR_PAYLOAD, **STANDALONE_EXTRA})

    assert response.status_code == 200, response.get_json()


def test_the_automation_off_choice_is_a_valid_interval(client):
    response = client.put("/api/v1/config", json={"wanted_search_interval_hours": "0"})

    assert response.status_code == 200, response.get_json()
