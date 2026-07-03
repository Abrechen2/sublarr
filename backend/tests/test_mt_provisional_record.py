"""Tests for services.mt_provisional (plan #8, Task 2).

finalize_translation always records the Sublarr-translated output as a
subtitle_downloads row flagged source="machine_translation". Whether the
wanted item is then kept "provisional" (still seeking the human original) or
deleted (current behaviour) is gated by the profile's
mt_keep_seeking_original flag -- and fails safe to delete on any
profile-resolution error. See docs/plans/2026-07-03-v1.6-provisional-mt.md.
"""

from __future__ import annotations

from db.models.providers import SubtitleDownload
from db.wanted import get_wanted_item, upsert_wanted_item
from extensions import db
from services import mt_provisional


def _make_wanted_item(tmp_path, target_language="de"):
    """Create a real wanted item in the test DB, return (id, item dict)."""
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(mkv),
        target_language=target_language,
    )
    return item_id, get_wanted_item(item_id)


def test_finalize_translation_keeps_provisional_when_profile_opts_in(
    app_ctx, tmp_path, monkeypatch
):
    """keep-seeking TRUE: MT row recorded AND wanted item stays 'provisional'."""
    monkeypatch.setattr(mt_provisional, "resolve_keep_seeking", lambda item: True)

    item_id, item = _make_wanted_item(tmp_path)
    output_path = str(tmp_path / "ep.de.ass")

    mt_provisional.finalize_translation(item_id, item, output_path, "de", "ass")

    row = db.session.query(SubtitleDownload).filter_by(source="machine_translation").one()
    assert row.language == "de"
    assert row.file_path == output_path
    assert row.score == 0

    updated = get_wanted_item(item_id)
    assert updated is not None
    assert updated["status"] == "provisional"


def test_finalize_translation_deletes_item_when_profile_opts_out(app_ctx, tmp_path, monkeypatch):
    """keep-seeking FALSE: MT row still recorded (flag always on) BUT item is deleted."""
    monkeypatch.setattr(mt_provisional, "resolve_keep_seeking", lambda item: False)

    item_id, item = _make_wanted_item(tmp_path)
    output_path = str(tmp_path / "ep.de.srt")

    mt_provisional.finalize_translation(item_id, item, output_path, "de", "srt")

    row = db.session.query(SubtitleDownload).filter_by(source="machine_translation").one()
    assert row.language == "de"
    assert row.file_path == output_path
    assert row.score == 0

    assert get_wanted_item(item_id) is None


def test_finalize_translation_fails_safe_to_delete_on_profile_resolution_error(
    app_ctx, tmp_path, monkeypatch
):
    """MT row still lands even when profile resolution blows up underneath
    the REAL (unmocked) resolve_keep_seeking -- and the item is deleted
    (fail-safe), proving resolve_keep_seeking's own try/except boundary works.
    """

    def _boom(item):
        raise RuntimeError("profile lookup exploded")

    monkeypatch.setattr(mt_provisional, "_resolve_profile_for_item", _boom)

    item_id, item = _make_wanted_item(tmp_path)
    output_path = str(tmp_path / "ep.de.ass")

    mt_provisional.finalize_translation(item_id, item, output_path, "de", "ass")

    row = db.session.query(SubtitleDownload).filter_by(source="machine_translation").one()
    assert row.file_path == output_path

    # Fails safe to delete when profile resolution errors out.
    assert get_wanted_item(item_id) is None


def test_resolve_keep_seeking_reads_flag_from_real_series_profile(app_ctx, tmp_path):
    """End-to-end (no monkeypatch): a real profile with the flag set on a series."""
    from db.models.core import LanguageProfile
    from db.profiles import assign_series_profile
    from db.repositories.profiles import ProfileRepository

    repo = ProfileRepository()
    profile_id = repo.create_profile(
        name="MT Keep Seeking Profile",
        source_lang="en",
        source_name="English",
        target_langs=["de"],
        target_names=["German"],
    )
    profile = db.session.get(LanguageProfile, profile_id)
    profile.mt_keep_seeking_original = 1
    db.session.commit()

    series_id = 424242
    assign_series_profile(series_id, profile_id)

    mkv = tmp_path / "series_ep.mkv"
    mkv.touch()
    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(mkv),
        target_language="de",
        sonarr_series_id=series_id,
    )
    item = get_wanted_item(item_id)

    assert mt_provisional.resolve_keep_seeking(item) is True


def test_resolve_keep_seeking_defaults_false_without_profile_assignment(app_ctx, tmp_path):
    """No series/movie assignment + no profiles at all -> synthetic default dict, no flag key."""
    item_id, item = _make_wanted_item(tmp_path)

    assert mt_provisional.resolve_keep_seeking(item) is False
