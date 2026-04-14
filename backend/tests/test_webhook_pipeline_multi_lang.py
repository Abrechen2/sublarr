"""Regression tests for the Sonarr/Radarr webhook auto-pipeline.

Covers:
  - The pipeline iterates ALL wanted items for a given file path (one per
    target language), not just the first one returned by the single-item
    lookup.
  - Download-without-translate: `process_wanted_item` is always invoked
    when `webhook_auto_search=True` regardless of `webhook_auto_translate`,
    because `process_wanted_item` handles the translate gate internally.
    The legacy branch that fell back to `search_wanted_item` (search only,
    no download) is gone — downloading is no longer coupled to translation.

All of `_webhook_auto_pipeline`'s imports live inside the function body
(lazy-import pattern), so the patches below target the source modules
(config.get_settings, db.wanted.get_wanted_items_by_path, etc.) rather
than the routes.webhooks module attributes.
"""

from types import SimpleNamespace
from unittest.mock import patch

import routes.webhooks as wh


def _settings_stub(**overrides):
    base = {
        "webhook_delay_minutes": 0,  # skip sleep in tests
        "webhook_auto_scan": False,  # skip scanner branch
        "webhook_auto_search": True,
        "webhook_auto_translate": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_pipeline_processes_every_language_for_one_path():
    """With de + en wanted items on the same path, both must be processed."""
    file_path = "/media/_Anime/_Serien/Show/S01E01.mkv"

    de_item = {"id": 11, "target_language": "de"}
    en_item = {"id": 12, "target_language": "en"}

    calls: list[int] = []

    def fake_process(item_id):
        calls.append(item_id)
        return {"status": "found", "wanted_id": item_id}

    with (
        patch("config.get_settings", return_value=_settings_stub()),
        patch("routes.webhooks.emit_event"),
        patch("routes.webhooks.socketio"),
        patch("db.wanted.get_wanted_items_by_path", return_value=[de_item, en_item]),
        patch("wanted_search.process_wanted_item", side_effect=fake_process),
        patch("notifier.send_notification"),
    ):
        wh._webhook_auto_pipeline(file_path=file_path, title="Show — S01E01", series_id=42)

    # Both items were handed to process_wanted_item
    assert sorted(calls) == [11, 12]


def test_pipeline_continues_when_one_language_raises():
    """One failing language must not prevent the other from being processed."""
    file_path = "/media/_Anime/_Serien/Show/S01E02.mkv"
    de_item = {"id": 21, "target_language": "de"}
    en_item = {"id": 22, "target_language": "en"}
    seen: list[int] = []

    def flaky_process(item_id):
        seen.append(item_id)
        if item_id == 21:
            raise RuntimeError("provider blew up for de")
        return {"status": "found", "wanted_id": item_id}

    with (
        patch("config.get_settings", return_value=_settings_stub()),
        patch("routes.webhooks.emit_event"),
        patch("routes.webhooks.socketio"),
        patch("db.wanted.get_wanted_items_by_path", return_value=[de_item, en_item]),
        patch("wanted_search.process_wanted_item", side_effect=flaky_process),
        patch("notifier.send_notification"),
    ):
        wh._webhook_auto_pipeline(file_path=file_path, title="Show — S01E02")

    # The failure on de must not short-circuit en.
    assert sorted(seen) == [21, 22]


def test_pipeline_logs_no_wanted_item_when_path_is_unknown():
    """No wanted item for the path → skip processing, no crash."""
    file_path = "/media/_Unknown/file.mkv"

    process_called: list[int] = []

    with (
        patch("config.get_settings", return_value=_settings_stub()),
        patch("routes.webhooks.emit_event"),
        patch("routes.webhooks.socketio"),
        patch("db.wanted.get_wanted_items_by_path", return_value=[]),
        patch("wanted_search.process_wanted_item", side_effect=process_called.append),
        patch("notifier.send_notification"),
    ):
        wh._webhook_auto_pipeline(file_path=file_path, title="Unknown")

    # Pipeline must not invoke process_wanted_item when no items match.
    assert process_called == []


def test_pipeline_download_runs_even_when_webhook_translate_is_disabled():
    """Regression for the prod config: translate is off, download must still run."""
    file_path = "/media/_Anime/_Serien/Show/S01E03.mkv"
    item = {"id": 30, "target_language": "de"}

    calls: list[int] = []

    def spy(item_id):
        calls.append(item_id)
        return {"status": "found"}

    with (
        patch(
            "config.get_settings",
            return_value=_settings_stub(webhook_auto_translate=False),
        ),
        patch("routes.webhooks.emit_event"),
        patch("routes.webhooks.socketio"),
        patch("db.wanted.get_wanted_items_by_path", return_value=[item]),
        patch("wanted_search.process_wanted_item", side_effect=spy),
        patch("notifier.send_notification"),
    ):
        wh._webhook_auto_pipeline(file_path=file_path, title="Show — S01E03")

    # process_wanted_item was still called despite webhook_auto_translate=False.
    # The translate gate is now inside process_wanted_item (reads
    # wanted_auto_translate), no longer at the webhook level.
    assert calls == [30]
