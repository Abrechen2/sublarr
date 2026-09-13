"""A Sublarr machine translation is the LAST resort, never a finished result.

Owner policy (2026-09-13): the best available subtitle must be kept, and a
subtitle Sublarr translated itself is never the best one. It must be replaced as
soon as a genuine provider/embedded original becomes available.

Two things stand in the way, and each gets a test here:

1. ``_check_language_for_item`` treats *any* ``.de.ass`` on disk as a finished
   result. Provenance is not on disk — it lives in
   ``subtitle_downloads.source == "machine_translation"`` — so an episode served
   by our own translation silently leaves the queue forever.

2. ``upsert_wanted_item`` cannot create a row in any state but ``wanted``, and a
   ``wanted`` row is picked up by ``wanted_search`` *with auto-translate*. Simply
   re-queuing a machine-translated episode would therefore re-translate the very
   file we want to replace — an endless MT loop. The re-queued row has to be
   ``provisional`` so ``services.mt_reseek`` owns it, which searches in
   original-only mode.

See docs/superpowers/specs/2026-09-13-machine-translation-is-last-resort-design.md
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 1. The scanner must not accept our own translation as the final answer
# ---------------------------------------------------------------------------


def test_machine_translated_ass_is_not_treated_as_satisfied():
    """An ASS we translated ourselves must be re-queued, not counted as done.

    The default (keep_seeking_mt=False) keeps today's behaviour — see the
    companion test below — so no existing caller changes meaning.
    """
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=True)
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="ass"),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=[]),
        patch(
            "services.wanted_item_scanner.is_machine_translated",
            return_value=True,
        ),
    ):
        result = _check_language_for_item(
            "/media/ep.mkv", "de", None, settings, keep_seeking_mt=True
        )

    assert result is not None, "a machine-translated ASS must not satisfy the target language"
    assert result["existing_sub"] == "ass"


def test_provider_ass_still_satisfies_the_target_language():
    """A genuine ASS is the best possible result and stays untouched."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=True)
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="ass"),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=[]),
        patch(
            "services.wanted_item_scanner.is_machine_translated",
            return_value=False,
        ),
    ):
        result = _check_language_for_item(
            "/media/ep.mkv", "de", None, settings, keep_seeking_mt=True
        )

    assert result is None


def test_keep_seeking_off_leaves_behaviour_unchanged():
    """With the gate closed an ASS satisfies the language, whatever its origin.

    This pins the HIGH-risk part of the change: two direct callers and the
    webhook pipeline reach this function, and none of them may shift meaning
    until they opt in explicitly.
    """
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=True)
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="ass"),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=[]),
        patch(
            "services.wanted_item_scanner.is_machine_translated",
            return_value=True,
        ),
    ):
        result = _check_language_for_item("/media/ep.mkv", "de", None, settings)

    assert result is None


# ---------------------------------------------------------------------------
# 2. A re-queued machine translation must land as provisional, not wanted
# ---------------------------------------------------------------------------


def test_upsert_can_create_a_provisional_row(app_ctx):
    """``upsert_wanted_item`` must accept a status, defaulting to "wanted".

    Without this a re-queued machine translation becomes a ``wanted`` row, and
    ``wanted_search`` re-translates it — the MT loop this whole change exists to
    prevent.

    Note the public wrapper in ``db.wanted`` forwards every argument
    *positionally*, so ``status`` has to be keyword-only to avoid shifting the
    existing arguments.
    """
    from db.wanted import upsert_wanted_item

    row_id, was_updated = upsert_wanted_item(
        item_type="episode",
        file_path="/media/mt-last-resort.mkv",
        title="MT last resort",
        target_language="de",
        existing_sub="ass",
        status="provisional",
    )

    assert was_updated is False

    from db.models.core import WantedItem
    from extensions import db

    row = db.session.get(WantedItem, row_id)
    assert row.status == "provisional"


def test_upsert_status_defaults_to_wanted(app_ctx):
    """Omitting the new argument must keep the existing insert behaviour."""
    from db.wanted import upsert_wanted_item

    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path="/media/mt-default-status.mkv",
        title="MT default status",
        target_language="de",
    )

    from db.models.core import WantedItem
    from extensions import db

    row = db.session.get(WantedItem, row_id)
    assert row.status == "wanted"
