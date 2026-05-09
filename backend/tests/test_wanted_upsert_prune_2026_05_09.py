"""Regression test for the 2026-05-09 wanted_upsert sibling-prune fix.

Background — when Sonarr swaps a file via a quality-upgrade
(e.g. ``…WEBRip-1080p.mkv`` → ``…WEBDL-1080p.mkv``), Sublarr's
``upsert_wanted_item`` matches on
``(file_path, target_language, subtitle_type)`` and therefore inserts a
fresh row for the new path while the old row is left orphaned.

Before this fix the orphaned row stayed in ``wanted_items`` forever
with ``error="File not found on disk"`` and ``status="failed"``
(set later by the search pipeline when it tried to read the missing
file). The UI showed the same episode twice — one ``Gesucht`` row for
the new file plus one ``Fehlgeschlagen`` row per language for the old
file.

The fix sweeps shadowed siblings in the same transaction as the
upsert: any sibling with the same logical entity (Sonarr episode /
Radarr movie / standalone series+S/E / standalone movie) and the same
``(target_language, subtitle_type)`` but a different ``file_path`` is
deleted when its file no longer exists on disk.

Mount-blip defence: the prune only runs when the freshly-upserted
``file_path`` actually exists on disk (proves the mount is reachable).
That's the same posture as the cleanup-executor C0-3 / standalone S0-1
fixes.
"""

from __future__ import annotations

import os


def test_prune_removes_stale_sonarr_sibling_after_quality_upgrade(tmp_path, app_ctx):
    """Sonarr WEBRip → WEBDL upgrade: the WEBRip row should be pruned."""
    from db.wanted import get_wanted_item, upsert_wanted_item

    old_path = tmp_path / "Show - S01E01 - Pilot WEBRip-1080p.mkv"
    new_path = tmp_path / "Show - S01E01 - Pilot WEBDL-1080p.mkv"
    old_path.touch()  # exists initially when WEBRip row is inserted
    old_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(old_path),
        target_language="de",
        sonarr_episode_id=12345,
    )
    assert get_wanted_item(old_id) is not None

    # Sonarr replaces WEBRip with WEBDL — old file is gone, new file lands
    old_path.unlink()
    new_path.touch()
    new_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(new_path),
        target_language="de",
        sonarr_episode_id=12345,
    )

    # New row exists, old row was pruned by the sibling-sweep
    assert get_wanted_item(new_id) is not None
    assert get_wanted_item(old_id) is None
    assert new_id != old_id


def test_prune_does_not_touch_siblings_with_existing_files(tmp_path, app_ctx):
    """Sibling rows whose file still exists are NOT pruned."""
    from db.wanted import get_wanted_item, upsert_wanted_item

    sib_path = tmp_path / "Show - S01E01 - Pilot WEBRip-1080p.mkv"
    new_path = tmp_path / "Show - S01E01 - Pilot WEBDL-1080p.mkv"
    sib_path.touch()
    new_path.touch()

    sib_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(sib_path),
        target_language="de",
        sonarr_episode_id=99,
    )
    new_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(new_path),
        target_language="de",
        sonarr_episode_id=99,
    )

    # Both files exist — both rows must survive
    assert get_wanted_item(sib_id) is not None
    assert get_wanted_item(new_id) is not None


def test_prune_respects_target_language_separation(tmp_path, app_ctx):
    """A DE-language sibling for the same episode must not be pruned by
    an EN-language upsert (and vice versa)."""
    from db.wanted import get_wanted_item, upsert_wanted_item

    de_path_old = tmp_path / "Show - S02E02 WEBRip.mkv"
    en_path_new = tmp_path / "Show - S02E02 WEBDL.mkv"
    de_path_old.touch()  # DE row points at this file (which will then disappear)

    de_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(de_path_old),
        target_language="de",
        sonarr_episode_id=42,
    )
    # EN-language row arrives for the new file path — different language
    # space, must NOT touch the DE row even though sonarr_episode_id matches.
    en_path_new.touch()
    en_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(en_path_new),
        target_language="en",
        sonarr_episode_id=42,
    )

    # DE row must survive — different target_language than the EN upsert.
    assert get_wanted_item(de_id) is not None
    assert get_wanted_item(en_id) is not None


def test_prune_skipped_when_keep_path_unreachable(tmp_path, app_ctx):
    """Mount-blip defence: if the freshly-upserted file path doesn't
    exist on disk, the prune sweep is skipped so a brief mount blip
    can't wrongly delete legacy rows.

    We reach into the mixin directly with a non-existent ``keep_file_path``
    and assert no rows are touched.
    """
    from db.repositories.wanted import WantedRepository
    from db.wanted import get_wanted_item, upsert_wanted_item

    legacy_path = tmp_path / "Legacy - S03E03 WEBRip.mkv"
    legacy_path.touch()

    legacy_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(legacy_path),
        target_language="de",
        sonarr_episode_id=7,
    )

    # Now simulate: media_path went unreachable, but caller still tries
    # to upsert a "new" file that doesn't exist on disk yet.
    legacy_path.unlink()  # legacy gone too
    bogus = tmp_path / "does_not_exist_yet.mkv"
    repo = WantedRepository()
    deleted = repo._prune_replaced_siblings(
        keep_id=99999,  # imaginary — no row matches
        keep_file_path=str(bogus),  # not on disk → mount-blip indicator
        target_language="de",
        subtitle_type="full",
        sonarr_episode_id=7,
        radarr_movie_id=None,
        standalone_series_id=None,
        standalone_movie_id=None,
        season_episode="",
    )
    # No prune attempted — legacy row would have been deleted otherwise
    # because the file is also gone, but the mount-blip guard short-circuits.
    assert deleted == 0
    assert get_wanted_item(legacy_id) is not None


def test_prune_handles_radarr_movies(tmp_path, app_ctx):
    """Same logic for Radarr-tracked movies: identity is radarr_movie_id."""
    from db.wanted import get_wanted_item, upsert_wanted_item

    old_path = tmp_path / "Movie BluRay-1080p.mkv"
    new_path = tmp_path / "Movie WEBDL-2160p.mkv"
    old_path.touch()
    old_id, _ = upsert_wanted_item(
        item_type="movie",
        file_path=str(old_path),
        target_language="de",
        radarr_movie_id=555,
    )
    old_path.unlink()
    new_path.touch()
    new_id, _ = upsert_wanted_item(
        item_type="movie",
        file_path=str(new_path),
        target_language="de",
        radarr_movie_id=555,
    )

    assert get_wanted_item(old_id) is None
    assert get_wanted_item(new_id) is not None


def test_prune_skipped_without_logical_identity(tmp_path, app_ctx):
    """Without sonarr_episode_id / radarr_movie_id / standalone IDs we
    can't safely identify siblings, so the prune is a no-op."""
    from db.wanted import get_wanted_item, upsert_wanted_item

    a_path = tmp_path / "A.mkv"
    b_path = tmp_path / "B.mkv"
    a_path.touch()
    b_path.touch()

    a_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(a_path),
        target_language="de",
    )
    a_path.unlink()  # A's file disappears

    # Upsert B without any logical identity — A must NOT get pruned
    # (no way to know A and B are the "same" episode).
    b_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(b_path),
        target_language="de",
    )

    assert get_wanted_item(a_id) is not None
    assert get_wanted_item(b_id) is not None


def test_prune_handles_path_separator_normalization(tmp_path, app_ctx):
    """Sibling whose file_path differs only in / vs \\\\ separators must
    NOT be pruned — that would be a self-delete via the match key."""
    from db.repositories.wanted import WantedRepository
    from db.wanted import get_wanted_item, upsert_wanted_item

    p = tmp_path / "subdir" / "ep.mkv"
    p.parent.mkdir()
    p.touch()
    posix_form = str(p).replace("\\", "/")
    native_form = os.path.normpath(str(p))

    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(p),
        target_language="de",
        sonarr_episode_id=11,
    )

    # Simulate a follow-up upsert that resolves to the same file via
    # a different separator form. Should be a no-op prune (no other row
    # exists; the existing one is the same logical entity by file_path).
    repo = WantedRepository()
    deleted = repo._prune_replaced_siblings(
        keep_id=row_id,
        keep_file_path=posix_form if os.sep == "\\" else native_form,
        target_language="de",
        subtitle_type="full",
        sonarr_episode_id=11,
        radarr_movie_id=None,
        standalone_series_id=None,
        standalone_movie_id=None,
        season_episode="",
    )
    assert deleted == 0
    assert get_wanted_item(row_id) is not None
