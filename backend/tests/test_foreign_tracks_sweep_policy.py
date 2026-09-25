"""Per-track verdicts, per-file policy, and the config hash (Task 7).

The batched sweep now stores a verdict per track in its probe phase, applies
the per-file policy (global + series/movie override by path) in probe and
strip, and folds the global policy into the config hash — the legacy default
must add nothing, so every verdict cache written before this feature existed
survives the upgrade.

Fix round 1 adds: `override_paths()` reporting resolution completeness so a
Sonarr/Radarr outage never lets the sweep strip more than configured
(strip is paused, not silently downgraded to the default policy); per-file
failures (bad policy resolution, bad verdict computation, a bad sidecar
lookup) folded into the same per-row try/except as the probe/remux itself,
so one bad file cannot stall the sweep; and the sidecar lookup gated on
BOTH policy B and one_per_language mode.
"""

import os

from db.models import foreign_tracks as ft
from services.foreign_tracks.select import MODE_ONE, SIDECAR_DROP, TrackPolicy
from services.foreign_tracks.state import config_hash

CFG = {"keep_languages": ["de", "en"], "keep_und": True}


def test_policy_change_changes_the_config_hash():
    cfg = {"keep_languages": ["de", "en"], "keep_und": False}
    assert config_hash(cfg, "/media") != config_hash(
        cfg, "/media", TrackPolicy(mode="one_per_language")
    )
    assert config_hash(cfg, "/media") == config_hash(cfg, "/media", TrackPolicy())


def test_probe_stores_per_track_verdicts(app_ctx, tmp_path):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    repo = ForeignTrackScanRepository()
    path = str(tmp_path / "e1.mkv")
    repo.upsert_seen(path, 10, 1.0, generation=1)
    verdicts = [
        {
            "index": 5,
            "sub_index": 1,
            "language": "en",
            "fmt": "image",
            "kind": "full",
            "keep": True,
            "reason": "kept_main",
        },
        {
            "index": 6,
            "sub_index": 2,
            "language": "en",
            "fmt": "image",
            "kind": "sdh",
            "keep": False,
            "reason": "stripped_variant",
        },
    ]
    repo.mark_probed_verdicts(path, verdicts)
    sample = repo.sample_affected(5)
    assert sample[0]["tracks"] == 1
    assert sample[0]["verdicts"] == verdicts


def test_the_sweep_decides_with_the_policy_of_the_file(app_ctx, tmp_path, monkeypatch):
    from services.foreign_tracks import sweep

    probe = {
        "streams": [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": "English"},
            },
            {
                "index": 3,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "disposition": {"hearing_impaired": 1},
                "tags": {"language": "eng", "title": "SDH"},
            },
        ]
    }
    policy = TrackPolicy(mode="one_per_language")
    verdicts = sweep._verdicts_for(str(tmp_path / "e1.mkv"), probe, {"en", "eng"}, False, policy)
    assert [v["keep"] for v in verdicts] == [True, False]


# ---------------------------------------------------------------------------
# Fix round 1, ruling 1: an unresolved series/movie override must never let
# the sweep strip more than configured. `override_paths()` now reports
# whether resolution was COMPLETE; strip is paused (not run under a
# possibly-wrong default policy) whenever it wasn't.
# ---------------------------------------------------------------------------


def test_incomplete_overrides_pause_strip_without_calling_strip_file(
    app_ctx, tmp_path, monkeypatch
):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks import sweep as sw

    repo = ForeignTrackScanRepository()
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])  # affected
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "override_paths", lambda: ([], False))
    called = []
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: called.append(1) or ("/trash.bak", 5))

    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert called == [], "an incomplete override resolution must never reach the rewrite"
    assert "override" in (result["paused_reason"] or "").lower()
    assert repo.counts_by_state()[ft.STATE_AFFECTED] == 1, "the row stays affected, not failed"


def test_complete_overrides_let_strip_run(app_ctx, tmp_path, monkeypatch):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks import sweep as sw

    repo = ForeignTrackScanRepository()
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])  # affected
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "override_paths", lambda: ([], True))
    called = []
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: called.append(1) or ("/trash.bak", 5))

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert called == [1]


# ---------------------------------------------------------------------------
# Fix round 1, ruling 3: the per-file override policy actually reaches BOTH
# the probe decision and the strip rewrite, and `override_paths()` is
# resolved only once for the whole slice even though it feeds both phases.
# ---------------------------------------------------------------------------


def test_the_slice_applies_the_folder_override_policy_end_to_end(app_ctx, tmp_path, monkeypatch):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks import sweep as sw

    repo = ForeignTrackScanRepository()
    folder = str(tmp_path / "Anime")
    path = os.path.join(folder, "e1.mkv")
    repo.upsert_seen(path, 10, 1.0, generation=1)

    override_policy = TrackPolicy(mode="one_per_language")
    calls = []

    def fake_override_paths():
        calls.append(1)
        return [(folder, override_policy)], True

    monkeypatch.setattr(sw, "override_paths", fake_override_paths)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda p: {
            "streams": [{"index": 1, "codec_type": "subtitle", "tags": {"language": "spa"}}]
        },
    )

    seen = {}

    def fake_verdicts_for(p, probe, keep_languages, keep_und, policy):
        seen["probe"] = policy
        return [
            {
                "index": 1,
                "sub_index": 0,
                "language": "spa",
                "fmt": "text",
                "kind": "full",
                "keep": False,
                "reason": "stripped_language",
            }
        ]

    monkeypatch.setattr(sw, "_verdicts_for", fake_verdicts_for)

    def fake_strip_file(p, keep, keep_und, policy=None, real_sidecar_langs=None):
        seen["strip"] = policy
        return ("/trash.bak", 5)

    monkeypatch.setattr(sw, "_strip_file", fake_strip_file)

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert seen["probe"] is override_policy
    assert seen["strip"] is override_policy
    assert len(calls) == 1, "override_paths() must be resolved once per slice, not per file"


# ---------------------------------------------------------------------------
# Fix round 1, ruling 2: one bad file must not stall the sweep. Policy
# resolution, verdict computation, and the sidecar lookup all now live
# inside the same per-row try/except as the probe/remux itself.
# ---------------------------------------------------------------------------


def test_a_verdicts_error_fails_only_that_row_and_probing_continues(app_ctx, tmp_path, monkeypatch):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks import sweep as sw

    repo = ForeignTrackScanRepository()
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.upsert_seen("/media/b.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_probe_file", lambda p: {"streams": []})

    def boom(path, probe, keep_languages, keep_und, policy):
        if path == "/media/a.mkv":
            raise RuntimeError("verdicts exploded")
        return []

    monkeypatch.setattr(sw, "_verdicts_for", boom)

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    counts = repo.counts_by_state()
    assert counts.get(ft.STATE_FAILED, 0) == 1
    assert counts.get(ft.STATE_CLEAN, 0) == 1, "the next row must still be probed"


def test_a_sidecar_lookup_error_fails_only_that_row_and_stripping_continues(
    app_ctx, tmp_path, monkeypatch
):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks import sweep as sw

    repo = ForeignTrackScanRepository()
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    repo.upsert_seen("/media/b.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/b.mkv", ["spa"])
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))

    def boom(path, keep_languages, policy):
        if path == "/media/a.mkv":
            raise RuntimeError("sidecar lookup exploded")
        return set()

    monkeypatch.setattr(sw, "_real_sidecars_for_policy", boom)
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: ("/trash.bak", 5))

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    counts = repo.counts_by_state()
    assert counts.get(ft.STATE_FAILED, 0) == 1
    assert counts.get(ft.STATE_STRIPPED, 0) == 1, "the next row must still be stripped"


# ---------------------------------------------------------------------------
# Fix round 1, ruling 4: the sidecar lookup only ever fires for policy B in
# one_per_language mode — select_tracks ignores real_sidecar_langs otherwise,
# so any other combination must never touch the DB/filesystem.
# ---------------------------------------------------------------------------


def test_real_sidecars_are_only_looked_up_for_policy_b_in_one_per_language_mode(monkeypatch):
    from services.foreign_tracks import sidecars
    from services.foreign_tracks import sweep as sw

    calls = []
    monkeypatch.setattr(
        sidecars, "real_sidecar_languages", lambda *a, **k: calls.append(1) or set()
    )

    all_mode_policy = TrackPolicy(mode="all", sidecar_policy=SIDECAR_DROP)
    assert sw._real_sidecars_for_policy("/media/a.mkv", {"en"}, all_mode_policy) == set()
    assert calls == [], "policy B outside one_per_language mode must never look sidecars up"

    one_mode_policy = TrackPolicy(mode=MODE_ONE, sidecar_policy=SIDECAR_DROP)
    sw._real_sidecars_for_policy("/media/a.mkv", {"en"}, one_mode_policy)
    assert calls == [1], "the mock must actually fire under mode=one_per_language + policy B"
