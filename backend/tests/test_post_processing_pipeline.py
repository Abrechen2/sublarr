"""Plan B6 — pipeline driver tests."""

import pytest


def test_base_op_abc_exists():
    from post_processing.base_op import BaseOp, OpResult

    with pytest.raises(TypeError):
        BaseOp()

    # OpResult is a dataclass
    result = OpResult(op_id="test", ok=True, duration_ms=5, message="")
    assert result.op_id == "test"
    assert result.ok is True


def test_register_op_decorator():
    from post_processing.base_op import _OP_REGISTRY, BaseOp, OpResult, register_op

    before = len(_OP_REGISTRY)

    @register_op
    class DummyOp(BaseOp):
        op_id = "dummy_b6_test"
        label = "Dummy"
        description = "test"

        def execute(self, context):
            return OpResult(op_id=self.op_id, ok=True, duration_ms=0, message="ran")

    assert len(_OP_REGISTRY) == before + 1
    assert "dummy_b6_test" in {cls.op_id for cls in _OP_REGISTRY}

    # Cleanup
    _OP_REGISTRY.remove(DummyOp)


def test_pipeline_runs_ops_in_order_and_writes_audit(tmp_path, app_ctx):
    """PostProcessingPipeline runs ops sequentially, catches exceptions, writes an audit row."""
    from post_processing.base_op import _OP_REGISTRY, BaseOp, OpResult, register_op
    from post_processing.pipeline import PostProcessingPipeline

    @register_op
    class FirstOp(BaseOp):
        op_id = "b6_first"
        label = "First"
        description = "test"

        def execute(self, context):
            return OpResult(
                op_id=self.op_id, ok=True, duration_ms=3, message="first-ran"
            )

    @register_op
    class FailingOp(BaseOp):
        op_id = "b6_failing"
        label = "Fail"
        description = "test"
        abort_on_error = False

        def execute(self, context):
            raise RuntimeError("boom")

    try:
        pipe = PostProcessingPipeline()
        context = {
            "subtitle_path": str(tmp_path / "s.srt"),
            "video_path": "/v.mkv",
            "lang": "en",
            "score": 100,
            "trigger": "after_download",
        }
        op_ids = ["b6_first", "b6_failing"]
        results = pipe.run(trigger="after_download", op_ids=op_ids, context=context)

        assert len(results) == 2
        assert results[0].ok is True
        assert results[1].ok is False  # caught exception

        # Audit row written
        from db.models.core import PostProcessingRun

        runs = (
            PostProcessingRun.query.order_by(PostProcessingRun.id.desc()).limit(5).all()
        )
        assert any(
            r.trigger == "after_download" and "b6_first" in str(r.ops_executed)
            for r in runs
        )
    finally:
        _OP_REGISTRY.remove(FirstOp)
        _OP_REGISTRY.remove(FailingOp)
