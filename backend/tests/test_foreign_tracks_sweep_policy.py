"""Per-track verdicts, per-file policy, and the config hash (Task 7).

The batched sweep now stores a verdict per track in its probe phase, applies
the per-file policy (global + series/movie override by path) in probe and
strip, and folds the global policy into the config hash — the legacy default
must add nothing, so every verdict cache written before this feature existed
survives the upgrade.
"""

from services.foreign_tracks.select import TrackPolicy
from services.foreign_tracks.state import config_hash


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
