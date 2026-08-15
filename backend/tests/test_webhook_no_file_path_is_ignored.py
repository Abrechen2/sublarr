"""An event with nothing to act on is not a malformed request.

Prod 2026-08-15: Sonarr v4.0.19 logged `Unable to send OnDownload notification
to: Sublarr` for every completed download, with

    [400:BadRequest] {"error":"No file path in webhook payload"}

400 means "your request was wrong". The request was fine — Sonarr had simply
nothing to hand over, because its own import had failed (173 failed imports,
0 successful, in the same 24h). Answering 4xx made Sonarr record the
notification as broken and hid the real fault behind webhook noise.

So the status code changes to 200/ignored. But silence would be worse than
the wrong code: the 400s were the only visible sign that the import path was
dead. The handler therefore logs the skip at WARNING, and names the payload's
top-level keys — which is also how we find out what a payload shape we have
never captured actually looks like, rather than guessing at Sonarr's schema.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


def _settings_mock(**overrides):
    defaults = {
        "api_key": "test-api-key",
        "media_path": "/media",
        "webhook_delay_minutes": 0,
        "webhook_auto_scan": False,
        "webhook_auto_search": False,
        "webhook_auto_translate": False,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


PAYLOADS = [
    pytest.param(
        "sonarr",
        {"eventType": "Download", "series": {"id": 1, "title": "T"}, "episodeFile": {}},
        id="sonarr_episodeFile_without_path",
    ),
    pytest.param(
        "sonarr",
        {"eventType": "Download", "series": {"id": 1, "title": "T"}},
        id="sonarr_episodeFile_missing_entirely",
    ),
    pytest.param(
        "sonarr",
        {"eventType": "Download", "series": {}, "episodeFile": {"path": ""}},
        id="sonarr_empty_path",
    ),
    pytest.param(
        "radarr",
        {"eventType": "Download", "movie": {"id": 1, "title": "F"}, "movieFile": {}},
        id="radarr_movieFile_without_path",
    ),
    pytest.param(
        "radarr",
        {"eventType": "Download", "movie": {"id": 1, "title": "F"}},
        id="radarr_movieFile_missing_entirely",
    ),
]


@pytest.mark.parametrize("service, payload", PAYLOADS)
def test_download_without_a_path_is_ignored_not_rejected(client, service, payload):
    with patch("config.get_settings", return_value=_settings_mock()):
        resp = client.post(
            f"/api/v1/webhook/{service}",
            json=payload,
            headers={"X-Api-Key": "test-api-key"},
        )

    assert resp.status_code == 200, (
        f"{service}: a Download event carrying no file is not a client error — "
        f"got {resp.status_code} {resp.get_data(as_text=True)!r}"
    )
    body = resp.get_json()
    assert body["status"] == "ignored"
    assert "file path" in body.get("reason", "").lower()
    assert "error" not in body


@pytest.mark.parametrize("service, payload", PAYLOADS)
def test_the_skip_is_logged_loudly_enough_to_notice(client, service, payload, caplog):
    """Silence would hide exactly what the 400s accidentally revealed.

    The 400 storm was the only reason the dead import path was ever noticed.
    Downgrading the status must not downgrade the visibility.
    """
    with (
        caplog.at_level(logging.WARNING),
        patch("config.get_settings", return_value=_settings_mock()),
    ):
        client.post(
            f"/api/v1/webhook/{service}",
            json=payload,
            headers={"X-Api-Key": "test-api-key"},
        )

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, f"{service}: skipping an event must not be silent"
    text = " ".join(r.getMessage() for r in warnings)
    assert "Download" in text, "the event type belongs in the line"


def test_payload_keys_are_named_so_an_unseen_shape_identifies_itself(client, caplog):
    """The log has to describe a payload nobody has seen before.

    This diagnostic earned its keep immediately: written while Sonarr's
    pathless payload was still unknown, it is what revealed the shape as
    `episodeFiles` (plural) plus fileCount/sourcePath/destinationPath — the
    import-summary companion, now recognised by name in
    test_webhook_import_complete_companion.py. The example here therefore uses
    a key that is still unknown, so the test keeps testing the unknown case
    rather than the one we since identified.
    """
    with (
        caplog.at_level(logging.WARNING),
        patch("config.get_settings", return_value=_settings_mock()),
    ):
        client.post(
            "/api/v1/webhook/sonarr",
            json={
                "eventType": "Download",
                "series": {"id": 1},
                "someFutureKey": {"relativePath": "x.mkv"},
            },
            headers={"X-Api-Key": "test-api-key"},
        )

    text = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "someFutureKey" in text, f"unknown key must be named, got: {text!r}"


def test_a_real_path_still_goes_through(client, tmp_path):
    """Guards the change: the accepting path must not have been widened."""
    media = tmp_path / "media"
    (media / "Show" / "Season 1").mkdir(parents=True)
    episode = media / "Show" / "Season 1" / "ep.mkv"
    episode.touch()

    with patch("config.get_settings", return_value=_settings_mock(media_path=str(media))):
        resp = client.post(
            "/api/v1/webhook/sonarr",
            json={
                "eventType": "Download",
                "series": {"id": 1, "title": "Show"},
                "episodeFile": {"path": str(episode)},
            },
            headers={"X-Api-Key": "test-api-key"},
        )

    assert resp.status_code in (200, 202), resp.get_data(as_text=True)
    assert resp.get_json().get("status") != "ignored"
