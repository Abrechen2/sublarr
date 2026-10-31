"""Everything the setup wizard saves is accepted by the real config endpoint.

Discord install-help 2026-10-31: since 1.14.0 PUT /config refuses unknown keys,
and the wizard still sent ``automation_enabled`` / ``search_interval_hours`` —
every step answered "Failed to save settings" and nothing, the path mapping
included, was stored.

The payloads are not a copy kept by hand (audit #61 S1): the frontend test
``OnboardingPayload.test.ts`` writes what ``buildOnboardingPayload`` really
produces to the contract file below and fails when the builder drifts from it.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

_CONTRACT = (
    Path(__file__).resolve().parents[2] / "frontend/src/test/__contracts__/onboarding-payload.json"
)
PAYLOADS = json.loads(_CONTRACT.read_text(encoding="utf-8"))


def _lan_address(*args, **kwargs):
    return [(2, 1, 6, "", ("192.168.10.40", 0))]


@pytest.mark.parametrize("case", sorted(PAYLOADS))
def test_the_wizard_payload_is_saved(client, case):
    payload = PAYLOADS[case]
    if case == "standalone":
        payload = {**payload, "standalone_enabled": "true"}  # added by the standalone step

    with patch("socket.getaddrinfo", side_effect=_lan_address):
        response = client.put("/api/v1/config", json=payload)

    assert response.status_code == 200, response.get_json()


def test_the_saved_values_are_the_running_settings(client):
    with patch("socket.getaddrinfo", side_effect=_lan_address):
        client.put("/api/v1/config", json=PAYLOADS["arr"])

    from config import get_settings

    settings = get_settings()
    assert settings.path_mapping == "/data/media=/media"
    assert settings.wanted_search_interval_hours == 6
    assert settings.upgrade_enabled is True
