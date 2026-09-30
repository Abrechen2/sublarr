"""The sweep's scope — include/exclude paths and the size limit — must hold
for the worklist it already has, not only for the next walk.

Prod 2026-09-28: the foreign_tracks rule was narrowed to ``include_paths:
["_Anime"]`` and ``foreign_track_sweep_max_file_gb`` set to 20. Both filter
only inside the walk. The config change reset the verdicts but, because the
previous walk had completed, jumped straight to PROBE over the old
whole-library worklist — so the next two nights remuxed 2160p films in
``_Filme`` (Sinners, Frozen, Bumblebee, Godzilla …) and the trash grew from
783 to 1421 GB. The state still named generation 1 from 2026-09-26; the new
scope would only have applied once that worklist drained, years away.
"""

import os
from types import SimpleNamespace

import pytest

from db.models import foreign_tracks as ft
from services.foreign_tracks import sweep as sw
from services.foreign_tracks.state import PHASE_STRIP, SweepState, config_hash, save_state

GB = 1024**3

CFG = {"keep_languages": ["de", "en"], "keep_und": True}
ANIME = dict(CFG, include_paths=["_Anime"])

SPANISH = {"streams": [{"index": 1, "codec_type": "subtitle", "tags": {"language": "spa"}}]}


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with an isolated SQLite DB for testing."""
    from app import create_app
    from config import reload_settings

    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True
    with application.app_context():
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


@pytest.fixture
def repo(app):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    return ForeignTrackScanRepository()


def _settings(monkeypatch, max_file_gb=0):
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            cleanup_foreign_tracks_keep_languages=["de", "en"],
            cleanup_foreign_tracks_keep_und=True,
            foreign_track_sweep_max_file_gb=max_file_gb,
        ),
    )


def _record_strips(monkeypatch) -> list[str]:
    stripped: list[str] = []

    def fake_strip(path, keep, keep_und, **kw):
        stripped.append(path)
        return ("/trash/x.bak", 5)

    monkeypatch.setattr(sw, "_strip_file", fake_strip)
    return stripped


def _record_walks(monkeypatch, files) -> list[list[str]]:
    """Each walk's include_paths, in order; every walk yields ``files``."""
    walks: list[list[str]] = []

    def fake_walk(root, include_paths, exclude_paths, **kw):
        walks.append(list(include_paths))
        return iter(files)

    monkeypatch.setattr(sw, "iter_video_files", fake_walk)
    return walks


def _prod_state_of_2026_09_28(root: str, config: dict) -> None:
    """A completed walk from before the scope existed, already in STRIP, and
    with the narrowed config already hashed — exactly what prod held."""
    save_state(
        SweepState(
            generation=1,
            phase=PHASE_STRIP,
            enumeration_complete=True,
            config_hash=config_hash(config, root),
        )
    )


class TestTheOldWorklistObeysTheScope:
    def test_an_affected_film_outside_include_paths_is_never_stripped(
        self, app, repo, tmp_path, monkeypatch
    ):
        root = str(tmp_path)
        film = os.path.join(root, "_Filme", "Sinners (2025)", "Sinners.mkv")
        episode = os.path.join(root, "_Anime", "Bleach", "S01E01.mkv")
        for path in (film, episode):
            repo.upsert_seen(path, 10, 1.0, generation=1)
            repo.mark_probed(path, ["spa"])
        _settings(monkeypatch)
        _prod_state_of_2026_09_28(root, ANIME)
        stripped = _record_strips(monkeypatch)
        _record_walks(monkeypatch, [])

        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)

        assert stripped == [episode]
        assert repo._get(film) is None, "an out-of-scope row must leave the worklist"

    def test_an_affected_file_over_the_size_limit_is_never_stripped(
        self, app, repo, tmp_path, monkeypatch
    ):
        root = str(tmp_path)
        film = os.path.join(root, "_Anime", "Film", "huge.mkv")
        episode = os.path.join(root, "_Anime", "Bleach", "S01E01.mkv")
        repo.upsert_seen(film, 70 * GB, 1.0, generation=1)
        repo.upsert_seen(episode, 1 * GB, 1.0, generation=1)
        for path in (film, episode):
            repo.mark_probed(path, ["spa"])
        _settings(monkeypatch, max_file_gb=20)
        _prod_state_of_2026_09_28(root, ANIME)
        stripped = _record_strips(monkeypatch)
        _record_walks(monkeypatch, [])

        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)

        assert stripped == [episode]
        assert repo._get(film) is None

    def test_a_pending_file_outside_the_scope_is_not_even_probed(
        self, app, repo, tmp_path, monkeypatch
    ):
        root = str(tmp_path)
        film = os.path.join(root, "_Filme", "Frozen (2013)", "Frozen.mkv")
        repo.upsert_seen(film, 10, 1.0, generation=1)
        _settings(monkeypatch)
        save_state(
            SweepState(
                generation=1,
                phase="probe",
                enumeration_complete=True,
                config_hash=config_hash(ANIME, root),
            )
        )
        probed: list[str] = []
        monkeypatch.setattr(sw, "_probe_file", lambda path: probed.append(path) or SPANISH)
        _record_strips(monkeypatch)
        _record_walks(monkeypatch, [])

        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)

        assert probed == []
        assert repo._get(film) is None


class TestAScopeChangeWalksAgain:
    def test_narrowing_include_paths_after_a_complete_walk_walks_again(
        self, app, repo, tmp_path, monkeypatch
    ):
        root = str(tmp_path)
        _settings(monkeypatch)
        monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
        walks = _record_walks(monkeypatch, [(os.path.join(root, "_Anime", "a.mkv"), 10, 1.0)])

        sw.run_slice(root, CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)

        assert walks == [[], ["_Anime"]]

    def test_widening_include_paths_walks_again_so_new_files_are_found(
        self, app, repo, tmp_path, monkeypatch
    ):
        """The mirror case: without a walk, a widened scope would only reach
        the new folders at the next rescan, `foreign_track_sweep_rescan_days`
        later."""
        root = str(tmp_path)
        _settings(monkeypatch)
        monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
        walks = _record_walks(monkeypatch, [])

        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)
        sw.run_slice(root, CFG, budget_s=60, now_fn=FakeClock(), repo=repo)

        assert walks == [["_Anime"], []]

    def test_changing_the_size_limit_walks_again_without_resetting_verdicts(
        self, app, repo, tmp_path, monkeypatch
    ):
        """The limit is not a verdict input — a clean file stays clean, it
        only needs the walk that applies the limit."""
        root = str(tmp_path)
        episode = os.path.join(root, "_Anime", "a.mkv")
        probed: list[str] = []
        monkeypatch.setattr(sw, "_probe_file", lambda path: probed.append(path) or {"streams": []})
        walks = _record_walks(monkeypatch, [(episode, 10, 1.0)])

        _settings(monkeypatch, max_file_gb=0)
        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)
        _settings(monkeypatch, max_file_gb=20)
        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)

        assert len(walks) == 2
        assert probed == [episode], "the size limit must not re-probe the library"
        assert repo.counts_by_state()[ft.STATE_CLEAN] == 1

    def test_a_keep_list_change_alone_still_skips_the_walk(self, app, repo, tmp_path, monkeypatch):
        """Unchanged behaviour: the files on disk did not change, only the
        verdicts — re-probing the worklist is enough."""
        root = str(tmp_path)
        _settings(monkeypatch)
        monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
        walks = _record_walks(monkeypatch, [(os.path.join(root, "_Anime", "a.mkv"), 10, 1.0)])

        sw.run_slice(root, ANIME, budget_s=60, now_fn=FakeClock(), repo=repo)
        sw.run_slice(
            root, dict(ANIME, keep_languages=["de"]), budget_s=60, now_fn=FakeClock(), repo=repo
        )

        assert walks == [["_Anime"]]
