"""Tests for services.retranslation finalize wiring.

The batch-translate path (POST /wanted/batch-translate -> retranslate_item ->
run_job -> translator.translate_file) is a translate-completion site that the
original provisional-MT plan (docs/plans/2026-07-03-v1.6-provisional-mt.md) did
NOT cover -- it ran the generic translation engine but never called
finalize_translation, so re-translated output was not flagged
source="machine_translation" and the wanted item was never set provisional.

_finalize_retranslation closes that gap. It must ONLY fire on a genuine
machine-translation result (success, not a skip, with an output path) -- never
on a skip (target already exists / provider ASS downloaded) or a failure.
"""

from __future__ import annotations

from db.models.providers import SubtitleDownload
from db.wanted import get_wanted_item, upsert_wanted_item
from extensions import db
from services import retranslation


def _make_item(tmp_path):
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(mkv),
        target_language="de",
    )
    return item_id, get_wanted_item(item_id)


def _mt_row_count() -> int:
    return db.session.query(SubtitleDownload).filter_by(source="machine_translation").count()


def test_finalize_flags_mt_and_keeps_provisional_on_real_translation(
    app_ctx, tmp_path, monkeypatch
):
    """A genuine MT result records the MT row and (keep-seeking on) stays provisional."""
    from services import mt_provisional

    monkeypatch.setattr(mt_provisional, "resolve_keep_seeking", lambda item: True)

    item_id, item = _make_item(tmp_path)
    out = str(tmp_path / "ep.de.ass")
    result = {
        "success": True,
        "output_path": out,
        "stats": {"format": "ass", "source": "embedded_ass"},
    }

    retranslation._finalize_retranslation(item_id, item, "de", result)

    row = db.session.query(SubtitleDownload).filter_by(source="machine_translation").one()
    assert row.file_path == out
    assert row.language == "de"
    assert row.score == 0
    assert get_wanted_item(item_id)["status"] == "provisional"


def test_finalize_noop_on_skip_result(app_ctx, tmp_path):
    """A skip (e.g. target already exists, or provider ASS downloaded in Case B1)
    must NOT be flagged as machine_translation and must leave the item untouched."""
    item_id, item = _make_item(tmp_path)
    result = {
        "success": True,
        "output_path": str(tmp_path / "ep.de.ass"),
        "stats": {"skipped": True, "reason": "German ASS already exists"},
    }

    retranslation._finalize_retranslation(item_id, item, "de", result)

    assert _mt_row_count() == 0
    assert get_wanted_item(item_id) is not None


def test_finalize_noop_on_failed_translation(app_ctx, tmp_path):
    item_id, item = _make_item(tmp_path)

    retranslation._finalize_retranslation(item_id, item, "de", {"success": False, "error": "boom"})

    assert _mt_row_count() == 0
    assert get_wanted_item(item_id) is not None


def test_finalize_noop_without_output_path(app_ctx, tmp_path):
    item_id, item = _make_item(tmp_path)
    result = {"success": True, "output_path": None, "stats": {"format": "srt"}}

    retranslation._finalize_retranslation(item_id, item, "de", result)

    assert _mt_row_count() == 0
    assert get_wanted_item(item_id) is not None


def test_finalize_noop_when_result_is_none(app_ctx, tmp_path):
    """run_job returns None when the job was cancelled/removed before execution."""
    item_id, item = _make_item(tmp_path)

    retranslation._finalize_retranslation(item_id, item, "de", None)

    assert _mt_row_count() == 0
    assert get_wanted_item(item_id) is not None
