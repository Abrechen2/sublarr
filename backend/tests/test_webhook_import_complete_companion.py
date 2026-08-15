"""The pathless Download event is a companion summary, not a failed import.

Captured on prod 2026-08-15 (Sonarr v4.0.19), the payload Sublarr could not
read:

    ['applicationUrl', 'destinationPath', 'downloadClient',
     'downloadClientType', 'downloadId', 'episodeFiles', 'episodes',
     'eventType', 'fileCount', 'instanceName', 'release', 'series',
     'sourcePath']

`episodeFiles` — plural. No singular `episodeFile`, which is the only key the
handler reads. And the events arrive strictly paired, within a second, for the
same series:

    16:21:05  Sonarr webhook: Rage of Bahamut      <- processed
    16:21:05  carried no file path                 <- skipped
    16:24:34  Sonarr webhook: Rage of Bahamut      <- processed
    16:24:34  carried no file path                 <- skipped

So Sonarr sends two notifications per import: OnDownload per file (singular
key, handled) and OnImportComplete for the operation (plural key, a summary of
files already announced individually). Both carry eventType "Download".

Nothing is lost by skipping the summary — but the first version of this skip
said "Sonarr's own import did not produce a file", which is false, and said it
at WARNING once per import. That turned a routine duplicate into a permanent
warning stream, which is precisely how a real webhook failure would come to be
overlooked.
"""

from unittest.mock import MagicMock, patch

import pytest

IMPORT_COMPLETE = {
    "eventType": "Download",
    "series": {"id": 1, "title": "Rage of Bahamut"},
    "episodes": [{"id": 10}],
    "episodeFiles": [{"id": 5, "relativePath": "S01E07.mkv"}],
    "fileCount": 1,
    "sourcePath": "/downloads/x",
    "destinationPath": "/tv/Rage of Bahamut",
    "downloadId": "abc",
}

UNKNOWN_SHAPE = {
    "eventType": "Download",
    "series": {"id": 1, "title": "Something"},
}


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


def _post(client, payload):
    with patch("config.get_settings", return_value=_settings_mock()):
        return client.post(
            "/api/v1/webhook/sonarr",
            json=payload,
            headers={"X-Api-Key": "test-api-key"},
        )


class TestCompanionSummaryIsRecognised:
    def test_still_answers_200_ignored(self, client):
        resp = _post(client, IMPORT_COMPLETE)
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_is_not_a_warning(self, client, caplog):
        """One per import forever is not a warning, it is a warning stream."""
        import logging

        with caplog.at_level(logging.DEBUG):
            _post(client, IMPORT_COMPLETE)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not warnings, (
            "a recognised, harmless duplicate must not warn — it arrives once "
            f"per import: {[r.getMessage() for r in warnings]}"
        )

    def test_does_not_claim_the_import_produced_nothing(self, client, caplog):
        """The wording that misled the author of this very handler."""
        import logging

        with caplog.at_level(logging.DEBUG):
            _post(client, IMPORT_COMPLETE)

        text = " ".join(r.getMessage() for r in caplog.records).lower()
        assert "did not produce a file" not in text
        assert "episodefiles" in text or "summary" in text or "already" in text


class TestGenuinelyUnknownShapeStaysLoud:
    def test_unrecognised_pathless_payload_still_warns(self, client, caplog):
        """The diagnostic that caught this must survive for the next surprise."""
        import logging

        with caplog.at_level(logging.DEBUG):
            resp = _post(client, UNKNOWN_SHAPE)

        assert resp.status_code == 200
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, "an unrecognised payload shape must still be visible"
        assert "Payload keys" in " ".join(r.getMessage() for r in warnings)


@pytest.mark.parametrize("plural_key", ["episodeFiles", "movieFiles"])
def test_empty_plural_list_is_not_treated_as_a_summary(client, caplog, plural_key):
    """An empty list carries no files, so it is not the companion case.

    Guards against recognising the shape by key alone and going quiet on a
    payload that really does announce nothing.
    """
    import logging

    payload = {"eventType": "Download", "series": {"id": 1}, plural_key: []}
    with caplog.at_level(logging.DEBUG):
        _post(client, payload)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "an empty file list is not a summary of imported files"
