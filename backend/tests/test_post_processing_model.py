"""Plan B6 — PostProcessingRun ORM sanity test."""

from datetime import UTC, datetime, timezone


def test_post_processing_run_has_expected_columns():
    from db.models.core import PostProcessingRun

    attrs = {"id", "trigger", "ops_executed", "duration_ms", "outcome", "created_at"}
    for attr in attrs:
        assert hasattr(PostProcessingRun, attr), f"missing {attr}"


def test_post_processing_run_instantiation():
    from db.models.core import PostProcessingRun

    row = PostProcessingRun(
        trigger="after_download",
        ops_executed={"ops": ["strip_html"]},
        duration_ms=42,
        outcome="ok",
        created_at=datetime.now(UTC),
    )
    assert row.trigger == "after_download"
    assert row.duration_ms == 42
    assert row.ops_executed == {"ops": ["strip_html"]}
