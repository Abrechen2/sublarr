"""The sweep must be a first-class scheduler job."""


def test_sweep_job_is_registered():
    from services.scheduler import _build_default_jobs

    spec = next(j for j in _build_default_jobs() if j.id == "foreign_track_sweep")
    assert spec.owner_module == "services.foreign_tracks.sweep"
    assert spec.max_instances == 1


def test_sweep_timeout_exceeds_the_default_budget():
    """A too-tight ceiling produced false 'timeout' rows for the cleanup job
    without ever protecting anything — future.result(timeout=) cannot cancel."""
    from config import get_settings
    from services.scheduler import _build_default_jobs

    spec = next(j for j in _build_default_jobs() if j.id == "foreign_track_sweep")
    budget = int(getattr(get_settings(), "foreign_track_sweep_budget_s", 1800))
    assert spec.timeout_s >= 2 * budget


def test_tick_is_picklable():
    """SQLAlchemyJobStore pickles jobs, so the tick must be a module-level
    callable with no closures."""
    import pickle

    from services.foreign_tracks.sweep import foreign_track_sweep_tick

    assert pickle.loads(pickle.dumps(foreign_track_sweep_tick)) is foreign_track_sweep_tick
