"""The usage_stats_ping job must be registered in the scheduler default set."""


def test_usage_stats_job_registered(app_ctx):
    from services.scheduler import _build_default_jobs

    ids = {spec.id for spec in _build_default_jobs()}
    assert "usage_stats_ping" in ids
