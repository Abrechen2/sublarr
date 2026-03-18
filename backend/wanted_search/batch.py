"""Wanted search batch operations and job queue integration."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import get_settings
from db.wanted import get_wanted_item, get_wanted_items
from wanted_search.process import process_wanted_item

logger = logging.getLogger(__name__)


def process_wanted_batch(item_ids=None, app=None):
    """Process multiple wanted items with parallel execution.

    Uses ThreadPoolExecutor for parallel processing. Provider-level rate
    limiters and circuit breakers handle concurrency safety. Error isolation
    ensures one item failure doesn't abort the batch.

    Args:
        item_ids: List of specific IDs, or None for all 'wanted' items.
        app: Flask app instance. Each worker thread pushes its own app context.

    Yields:
        Progress dicts for each item processed.
    """
    settings = get_settings()
    max_attempts = settings.wanted_max_search_attempts

    if item_ids:
        items = []
        for iid in item_ids:
            item = get_wanted_item(iid)
            if item:
                items.append(item)
    else:
        result = get_wanted_items(page=1, per_page=10000, status="wanted")
        items = result.get("data", [])

    # Filter out items that exceeded max search attempts
    items = [i for i in items if i["search_count"] < max_attempts]

    total = len(items)
    processed = 0
    found = 0
    failed = 0
    skipped = 0

    def _run_item(item_id):
        if app is not None:
            with app.app_context():
                return process_wanted_item(item_id)
        return process_wanted_item(item_id)

    max_workers = min(4, total) if total > 0 else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(_run_item, item["id"]): item for item in items}

        for future in as_completed(future_to_item):
            item = future_to_item[future]
            item_id = item["id"]
            display = item.get("title", item.get("file_path", str(item_id)))

            try:
                result = future.result()
                processed += 1

                if result.get("status") == "found":
                    found += 1
                elif result.get("status") == "failed":
                    failed += 1
                else:
                    skipped += 1

                yield {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "skipped": skipped,
                    "current_item": display,
                    "last_result": result,
                }

            except Exception as e:
                processed += 1
                failed += 1
                logger.exception("Batch: error processing wanted %d: %s", item_id, e)
                yield {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "skipped": skipped,
                    "current_item": display,
                    "last_result": {"wanted_id": item_id, "status": "failed", "error": str(e)},
                }


def _get_job_queue():
    """Get the app-level job queue backend, or None.

    Uses Flask's current_app to access the job_queue. Returns None if called
    outside Flask context or if job_queue is not configured. Never raises.
    """
    try:
        from flask import current_app

        return getattr(current_app, "job_queue", None)
    except (RuntimeError, ImportError):
        return None


def submit_wanted_search(item_id, job_id=None):
    """Submit a wanted search job via the app job queue.

    When a job queue is available (RQ with Redis, or MemoryJobQueue), the
    process_wanted_item function is enqueued for background execution. When
    no queue is available, falls back to direct synchronous execution.

    For the MemoryJobQueue fallback, this behaves identically to the current
    ThreadPoolExecutor pattern. For RQ, jobs survive container restarts and
    can be monitored via the queue API.

    Args:
        item_id: Wanted item ID to process.
        job_id: Optional custom job ID. Defaults to "wanted-{item_id}".

    Returns:
        str: Job ID if enqueued via queue, or the result dict if executed directly.
    """
    queue = _get_job_queue()
    if queue:
        try:
            _job_id = job_id or f"wanted-{item_id}"
            return queue.enqueue(
                process_wanted_item,
                item_id,
                job_id=_job_id,
            )
        except Exception as e:
            logger.warning(
                "Job queue submission failed for wanted %d, executing directly: %s", item_id, e
            )

    # Fallback: direct synchronous execution
    return process_wanted_item(item_id)


def submit_wanted_batch_search(item_ids=None):
    """Submit wanted batch search jobs via the app job queue.

    When a job queue is available, each item is submitted as a separate job
    for independent execution and monitoring. When no queue is available,
    falls back to the existing process_wanted_batch() generator.

    Args:
        item_ids: List of specific item IDs, or None for all 'wanted' items.

    Returns:
        list[str]: List of job IDs if enqueued via queue, or processes directly.
    """
    queue = _get_job_queue()
    if queue and item_ids:
        try:
            return [
                queue.enqueue(
                    process_wanted_item,
                    iid,
                    job_id=f"wanted-{iid}",
                )
                for iid in item_ids
            ]
        except Exception as e:
            logger.warning("Job queue batch submission failed, executing directly: %s", e)

    # Fallback: direct execution via existing batch processor
    results = []
    for progress in process_wanted_batch(item_ids):
        results.append(progress)
    return results
