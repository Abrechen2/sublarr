"""Tests for the provisional-MT re-seek job (feature #8b, Phase 2 — Task 1).

Covers:
- ``WantedRepository.get_provisional_items`` — selects ONLY ``status="provisional"``
  rows (a ``wanted`` item must never be picked by this job) and honours the
  per-item backoff cutoff.
- ``reseek_provisional_items`` — runs the normal search pipeline for each
  provisional item in ORIGINAL-ONLY mode (``auto_translate=False``), fires the
  ``_on_original_found`` hook on a found original, and bumps ``last_search_at``
  (leaving the item provisional) on a miss.

The re-seek loop tests mock the DB/repo + ``process_wanted_item`` exactly like
``tests/test_upgrade_scheduler.py`` so they need neither disk nor a real search.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from db.models.core import WantedItem
from extensions import db

# ── Repository selection (real DB via app_ctx) ───────────────────────────────


def _make_wanted_item(**kwargs) -> WantedItem:
    """Insert a minimal WantedItem; returns the persisted row."""
    now = datetime(2026, 7, 5, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/media/reseek_{id(kwargs):x}.mkv",
        title="Test",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    item = WantedItem(**defaults)
    db.session.add(item)
    db.session.commit()
    return item


def test_set_mt_pinned_and_set_mt_pending_original_round_trip(app_ctx):
    """DB round-trip for the two Task-2 repo helpers backing the pin signal
    and the notify pending-original marker (WantedRepository.set_mt_pinned /
    set_mt_pending_original, migration 3c4b1a2d5e6f)."""
    from db.wanted import get_wanted_item, set_mt_pending_original, set_mt_pinned

    item = _make_wanted_item(file_path="/media/pin_roundtrip.mkv")
    assert get_wanted_item(item.id)["mt_pinned"] in (0, None)

    assert set_mt_pinned(item.id, True) is True
    assert get_wanted_item(item.id)["mt_pinned"] == 1
    assert set_mt_pinned(item.id, False) is True
    assert get_wanted_item(item.id)["mt_pinned"] == 0
    assert set_mt_pinned(999999, True) is False  # unknown id — no exception

    assert get_wanted_item(item.id)["mt_pending_original"] is None
    assert set_mt_pending_original(item.id, '{"provider": "acme"}') is True
    assert get_wanted_item(item.id)["mt_pending_original"] == '{"provider": "acme"}'
    assert set_mt_pending_original(item.id, None) is True
    assert get_wanted_item(item.id)["mt_pending_original"] is None


def test_get_provisional_items_selects_only_provisional(app_ctx):
    from db.repositories.wanted import WantedRepository

    prov = _make_wanted_item(file_path="/media/prov.mkv", status="provisional")
    _make_wanted_item(file_path="/media/wanted.mkv", status="wanted")
    _make_wanted_item(file_path="/media/done.mkv", status="found")

    rows = WantedRepository().get_provisional_items(limit=10)

    ids = {r["id"] for r in rows}
    assert ids == {prov.id}
    assert all(r["status"] == "provisional" for r in rows)


def test_get_provisional_items_respects_backoff(app_ctx):
    from db.repositories.wanted import WantedRepository

    now = datetime.now(UTC)
    recent = _make_wanted_item(
        file_path="/media/recent.mkv",
        status="provisional",
        last_search_at=now - timedelta(hours=1),
    )
    old = _make_wanted_item(
        file_path="/media/old.mkv",
        status="provisional",
        last_search_at=now - timedelta(hours=48),
    )
    never = _make_wanted_item(
        file_path="/media/never.mkv",
        status="provisional",
        last_search_at=None,
    )

    cutoff = now - timedelta(hours=24)
    rows = WantedRepository().get_provisional_items(limit=10, search_cutoff=cutoff)

    ids = {r["id"] for r in rows}
    assert old.id in ids
    assert never.id in ids
    assert recent.id not in ids  # searched too recently → backed off


# ── Re-seek loop (mocked DB/repo/search, mirrors test_upgrade_scheduler) ──────


def _run_reseek(items, process_status="not_found", keep_seeking=True):
    """Run reseek_provisional_items with mocked DB, repo, and search entry.

    Returns (result, calls, mock_update, mock_hook) where ``calls`` is the list
    of (item_id, auto_translate, dry_run, bypass_existing_target_check) tuples
    passed to ``process_wanted_item``. Task 2's ``_reseek`` always previews
    with ``dry_run=True, bypass_existing_target_check=True`` before deciding
    what to do — see ``tests/test_wanted_search_dry_run.py`` for direct
    coverage of ``process_wanted_item``'s ``dry_run`` contract itself.
    """
    # Import for real BEFORE patching config.get_settings below. wanted_search
    # (and its process submodule) binds `get_settings` at module-import time
    # (`from config import get_settings`); if this is the first time it's ever
    # imported in the test process and that happens while config.get_settings
    # is patched, the module-level name is permanently poisoned to the mock
    # for the rest of the run (bites other test files depending on collection
    # order/xdist scheduling). Force the real import first so later patching
    # only affects mt_reseek's own lazy `from config import get_settings`.
    import wanted_search.process  # noqa: F401

    calls: list = []

    def fake_process(
        item_id, auto_translate=None, dry_run=False, bypass_existing_target_check=False
    ):
        calls.append((item_id, auto_translate, dry_run, bypass_existing_target_check))
        result = {"wanted_id": item_id, "status": process_status}
        if process_status == "found":
            result.update({"provider": "test_provider", "score": 50, "output_path": "/m/x.de.ass"})
        return result

    mock_repo = MagicMock()
    mock_repo.get_provisional_items.return_value = items

    settings = MagicMock()
    settings.wanted_search_interval_hours = 24
    settings.mt_reseek_max_items_per_run = 50

    with (
        patch("config.get_settings", return_value=settings),
        patch("db.repositories.wanted.WantedRepository", return_value=mock_repo),
        patch("wanted_search.process_wanted_item", side_effect=fake_process),
        patch("services.mt_provisional.resolve_keep_seeking", return_value=keep_seeking),
        patch("db.wanted.update_wanted_search_outcome") as mock_update,
        patch("services.mt_reseek._on_original_found") as mock_hook,
    ):
        from services.mt_reseek import reseek_provisional_items

        result = reseek_provisional_items(MagicMock())
    return result, calls, mock_update, mock_hook


def test_reseek_searches_provisional_with_auto_translate_false():
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 7, "status": "provisional"}], process_status="not_found"
    )

    # Provisional item was searched — exactly once, with translation disabled,
    # as a dry-run preview that also bypasses the existing-sidecar gate (the
    # MT sidecar IS the existing target-language file).
    assert calls == [(7, False, True, True)]
    assert result["searched"] == 1
    assert result["found"] == 0
    # On a miss the on-found hook must NOT fire...
    assert not mock_hook.called
    # ...and last_search_at is bumped while the item stays provisional.
    assert mock_update.called
    _, kwargs = mock_update.call_args
    assert kwargs.get("status") == "provisional"
    assert kwargs.get("last_search_at") is not None


def test_reseek_fires_hook_when_original_found():
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 9, "status": "provisional"}], process_status="found"
    )

    assert calls == [(9, False, True, True)]
    assert result["found"] == 1
    assert mock_hook.called  # Task-2 replace/notify hook wired at the call site
    assert not mock_update.called  # found path does NOT bump last_search_at


def test_reseek_skips_when_profile_no_longer_keep_seeking():
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 3, "status": "provisional"}], keep_seeking=False
    )

    # Profile turned keep-seeking off → item is not searched at all.
    assert calls == []
    assert result["searched"] == 0
    assert result["skipped"] == 1
    assert not mock_hook.called


def test_reseek_skips_pinned_item():
    """A pinned (user-edited/confirmed) MT is never searched at all — extends
    the Task-1 selection wiring with the Task-2 pinning signal."""
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 5, "status": "provisional", "mt_pinned": 1}]
    )

    assert calls == []
    assert result["searched"] == 0
    assert result["skipped"] == 1
    assert not mock_hook.called


def test_reseek_unpinned_item_with_falsy_flag_is_still_searched():
    """Regression: mt_pinned=0 (the column default) must not be treated as pinned."""
    result, calls, _mock_update, _mock_hook = _run_reseek(
        [{"id": 6, "status": "provisional", "mt_pinned": 0}], process_status="not_found"
    )

    assert calls == [(6, False, True, True)]
    assert result["searched"] == 1


# ── Task 2: on-found dispatch (auto_replace / notify / min-score gate) ──────


def _preview(**overrides):
    base = {
        "wanted_id": 1,
        "status": "found",
        "dry_run": True,
        "provider": "test_provider",
        "score": 50,
        "output_path": "/media/show/ep.de.ass",
        "format": "ass",
    }
    base.update(overrides)
    return base


def test_on_original_found_dispatches_to_auto_replace(monkeypatch):
    from services.mt_reseek import _on_original_found

    monkeypatch.setattr(
        "services.mt_provisional._resolve_profile_for_item",
        lambda item: {"mt_on_original_found": "auto_replace", "mt_min_original_score": 1},
    )
    replace_calls = []
    notify_calls = []
    monkeypatch.setattr(
        "services.mt_reseek._replace_original",
        lambda item, preview: replace_calls.append((item, preview)),
    )
    monkeypatch.setattr(
        "services.mt_reseek._record_pending_notification",
        lambda item, preview: notify_calls.append((item, preview)),
    )

    item = {"id": 1}
    preview = _preview()
    _on_original_found(item, preview)

    assert replace_calls == [(item, preview)]
    assert notify_calls == []


def test_on_original_found_dispatches_to_notify_by_default(monkeypatch):
    """A profile missing mt_on_original_found (predates the feature) defaults
    to the safer 'notify' behaviour."""
    from services.mt_reseek import _on_original_found

    monkeypatch.setattr(
        "services.mt_provisional._resolve_profile_for_item",
        lambda item: {"mt_min_original_score": 1},
    )
    replace_calls = []
    notify_calls = []
    monkeypatch.setattr(
        "services.mt_reseek._replace_original", lambda item, preview: replace_calls.append(1)
    )
    monkeypatch.setattr(
        "services.mt_reseek._record_pending_notification",
        lambda item, preview: notify_calls.append(1),
    )

    _on_original_found({"id": 2}, _preview())

    assert replace_calls == []
    assert notify_calls == [1]


def test_on_original_found_below_min_score_is_treated_as_miss(monkeypatch):
    from services.mt_reseek import _on_original_found

    monkeypatch.setattr(
        "services.mt_provisional._resolve_profile_for_item",
        lambda item: {"mt_on_original_found": "auto_replace", "mt_min_original_score": 60},
    )
    replace_calls = []
    notify_calls = []
    miss_calls = []
    monkeypatch.setattr(
        "services.mt_reseek._replace_original", lambda item, preview: replace_calls.append(1)
    )
    monkeypatch.setattr(
        "services.mt_reseek._record_pending_notification",
        lambda item, preview: notify_calls.append(1),
    )
    monkeypatch.setattr(
        "services.mt_reseek._mark_reseek_miss", lambda item_id: miss_calls.append(item_id)
    )

    _on_original_found({"id": 3}, _preview(score=50))  # below the 60 floor

    assert replace_calls == []
    assert notify_calls == []
    assert miss_calls == [3]


# ── Task 2: _replace_original (auto_replace) ────────────────────────────────


def test_replace_original_trashes_then_reruns_for_real(monkeypatch):
    from services.mt_reseek import _replace_original

    trash_calls = []
    monkeypatch.setattr(
        "services.mt_reseek._trash_existing_mt_file", lambda path: trash_calls.append(path)
    )

    process_calls = []

    def fake_process(
        item_id, auto_translate=None, dry_run=False, bypass_existing_target_check=False
    ):
        process_calls.append((item_id, auto_translate, dry_run, bypass_existing_target_check))
        return {"wanted_id": item_id, "status": "found", "provider": "real_provider"}

    monkeypatch.setattr("wanted_search.process_wanted_item", fake_process)

    item = {"id": 11}
    preview = _preview(output_path="/media/show/ep.de.ass")
    _replace_original(item, preview)

    # Trash happens BEFORE the real (non-preview) write.
    assert trash_calls == ["/media/show/ep.de.ass"]
    assert process_calls == [(11, False, False, True)]


def test_replace_original_miss_on_second_pass_marks_reseek_miss(monkeypatch):
    """Rare race: the preview found something but the real re-run came up
    empty. The MT copy is already safely trashed — treat it as a miss."""
    from services.mt_reseek import _replace_original

    monkeypatch.setattr("services.mt_reseek._trash_existing_mt_file", lambda path: None)
    monkeypatch.setattr(
        "wanted_search.process_wanted_item",
        lambda *a, **kw: {"wanted_id": 11, "status": "not_found"},
    )
    miss_calls = []
    monkeypatch.setattr(
        "services.mt_reseek._mark_reseek_miss", lambda item_id: miss_calls.append(item_id)
    )

    _replace_original({"id": 11}, _preview())

    assert miss_calls == [11]


# ── Task 2: _record_pending_notification (notify) ───────────────────────────


def test_record_pending_notification_sets_payload_and_restores_provisional(monkeypatch):
    import json

    from services.mt_reseek import _record_pending_notification

    set_calls = []
    status_calls = []
    monkeypatch.setattr(
        "db.wanted.set_mt_pending_original",
        lambda item_id, payload: set_calls.append((item_id, payload)),
    )
    monkeypatch.setattr(
        "db.wanted.update_wanted_status",
        lambda item_id, status: status_calls.append((item_id, status)),
    )

    preview = _preview(provider="acme", score=42, output_path="/m/ep.de.srt", format="srt")
    _record_pending_notification({"id": 20}, preview)

    assert status_calls == [(20, "provisional")]
    assert len(set_calls) == 1
    item_id, payload = set_calls[0]
    assert item_id == 20
    decoded = json.loads(payload)
    assert decoded["provider"] == "acme"
    assert decoded["score"] == 42
    assert decoded["output_path"] == "/m/ep.de.srt"
    assert decoded["format"] == "srt"
    assert "found_at" in decoded


# ── Task 2: end-to-end auto_replace (real DB + real trash, mocked provider) ─


class TestAutoReplaceIntegration:
    """Real WantedItem + real MT sidecar file on disk + real subtitle_downloads
    MT row + a real LanguageProfile with mt_on_original_found='auto_replace'.
    ``process_wanted_item`` runs for real (only the provider-manager boundary
    is mocked, matching ``tests/test_wanted_search.py``'s
    ``TestSaveSubtitleReturnPathPropagated`` convention) so the actual
    preview -> trash -> real-write sequence in services.mt_reseek is
    exercised end to end."""

    def test_auto_replace_trashes_mt_and_installs_original(self, app_ctx, monkeypatch, tmp_path):
        from config import get_settings
        from db.models.core import LanguageProfile, SeriesLanguageProfile
        from db.providers import record_subtitle_download
        from db.repositories.profiles import ProfileRepository

        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        mt_path = tmp_path / "ep.de.ass"
        mt_path.write_bytes(b"MT-CONTENT")

        item = _make_wanted_item(file_path=str(mkv), status="provisional", sonarr_series_id=42)
        item_id = item.id
        record_subtitle_download(
            "translation",
            "mt:ep.de.ass",
            "de",
            "ass",
            str(mt_path),
            0,
            source="machine_translation",
            record_stats=False,
        )

        profile_id = ProfileRepository().create_profile(
            name="auto-replace-profile",
            source_lang="en",
            source_name="English",
            target_langs=["de"],
            target_names=["German"],
        )
        profile = db.session.get(LanguageProfile, profile_id)
        profile.mt_keep_seeking_original = 1
        profile.mt_on_original_found = "auto_replace"
        profile.mt_min_original_score = 1
        db.session.add(SeriesLanguageProfile(sonarr_series_id=42, profile_id=profile_id))
        db.session.commit()

        real_result = MagicMock()
        real_result.provider_name = "realprovider"
        real_result.subtitle_id = "real123"
        real_result.language = "de"
        real_result.format.value = "ass"
        real_result.score = 80
        real_result.content = b"REAL-ORIGINAL-CONTENT"

        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = real_result

        def _fake_save(result, output_path, series_id=None):
            with open(output_path, "wb") as fh:
                fh.write(result.content)
            return output_path

        mock_mgr.save_subtitle.side_effect = _fake_save

        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)
        monkeypatch.setattr("nfo_export.maybe_write_nfo", lambda *a, **kw: None)
        monkeypatch.setattr("wanted_search.process._try_auto_sync", lambda *a, **kw: None)
        # trash_sidecar's is_safe_path guard checks the file is under
        # settings.media_path — point it at tmp_path for this test.
        monkeypatch.setattr(get_settings(), "media_path", str(tmp_path))

        from services.mt_reseek import reseek_provisional_items

        result = reseek_provisional_items(app_ctx)

        assert result["found"] == 1
        # The new original landed at the same path the MT used to occupy.
        assert mt_path.read_bytes() == b"REAL-ORIGINAL-CONTENT"
        # The old MT bytes are recoverable in the trash, not annihilated.
        trash_root = tmp_path / ".sublarr_trash"
        assert trash_root.is_dir()
        trashed_files = list(trash_root.rglob("ep.de.ass"))
        assert len(trashed_files) == 1
        assert trashed_files[0].read_bytes() == b"MT-CONTENT"
        # The wanted item was resolved (deleted) by the real success path.
        from db.wanted import get_wanted_item

        assert get_wanted_item(item_id) is None
