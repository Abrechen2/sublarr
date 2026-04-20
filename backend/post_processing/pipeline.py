"""Post-processing pipeline driver (Plan B6)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from post_processing.base_op import _OP_REGISTRY, BaseOp, OpResult
from post_processing.events import write_post_processing_run

logger = logging.getLogger(__name__)


def _configure_op_instance(instance: BaseOp) -> None:
    """Populate per-op config fields on ``instance`` before execute().

    Reads the stored values from ``config_entries`` via
    :func:`post_processing.config_store.get_op_config`, then ``setattr``s
    each known schema field on the instance. Fields absent from storage
    keep the class default (typically empty string, which triggers the
    op's own "not configured" fail-closed branch).

    Never raises — a DB or import failure logs a warning and leaves the
    instance on its class defaults.
    """
    try:
        from post_processing.config_store import get_op_config

        stored = get_op_config(instance.op_id)
        for entry in instance.config_schema:
            field = entry.get("key")
            if not field:
                continue
            if field in stored:
                setattr(instance, field, stored[field])
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "_configure_op_instance(%s) failed: %s",
            getattr(instance, "op_id", "?"),
            exc,
        )


class PostProcessingPipeline:
    """Synchronous pipeline runner — runs ops in order, catches exceptions, writes audit."""

    def run(
        self,
        trigger: str,
        op_ids: list[str],
        context: dict,
    ) -> list[OpResult]:
        """Run the ordered list of op_ids for this trigger.

        Returns per-op results. Writes one audit row per run.
        Never raises — failures are captured in ``OpResult.ok=False``.
        """
        start = time.monotonic()
        results: list[OpResult] = []

        # Resolve op_ids to classes (skip unknowns with a warning)
        by_id = {cls.op_id: cls for cls in _OP_REGISTRY}
        for op_id in op_ids:
            cls = by_id.get(op_id)
            if cls is None:
                logger.warning("Unknown post-processing op: %s", op_id)
                continue

            op_start = time.monotonic()
            try:
                instance = cls()
                _configure_op_instance(instance)
                result = instance.execute(context)
                results.append(result)
                if not result.ok and cls.abort_on_error:
                    logger.info(
                        "Aborting pipeline — %s failed with abort_on_error=True",
                        op_id,
                    )
                    break
            except Exception as exc:
                elapsed = int((time.monotonic() - op_start) * 1000)
                logger.warning("Op %s raised: %s", op_id, exc)
                results.append(
                    OpResult(op_id=op_id, ok=False, duration_ms=elapsed, message=str(exc))
                )
                if cls.abort_on_error:
                    break

        total_ms = int((time.monotonic() - start) * 1000)
        write_post_processing_run(trigger, results, total_ms)
        return results


_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """Return the shared ThreadPoolExecutor for post-processing runs.

    Lazy-initialized singleton with ``max_workers=2``; the dedicated pool
    keeps request handlers from blocking on slow ops (HTTP calls, scripts).
    """
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="post_proc")
    return _executor


def shutdown_executor(wait: bool = False) -> None:
    """Tear down the shared executor. Called from app shutdown hooks."""
    global _executor
    if _executor is not None:
        try:
            _executor.shutdown(wait=wait, cancel_futures=True)
        except Exception as exc:  # pragma: no cover
            logger.warning("post_processing executor shutdown failed: %s", exc)
        _executor = None


def run_trigger(trigger: str, op_ids: list[str], context: dict) -> None:
    """Fire-and-forget pipeline run on the shared thread pool.

    Use this from save paths — it returns immediately.
    """
    if not op_ids:
        return
    pipe = PostProcessingPipeline()
    _get_executor().submit(pipe.run, trigger, op_ids, context)
