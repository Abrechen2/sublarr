"""In-memory job queue using ThreadPoolExecutor.

Fallback when Redis/RQ is not available. Jobs are executed in-process
via a thread pool. Jobs do NOT persist across container restarts.
This matches the current Sublarr behavior (daemon threads).
"""

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from job_queue import JobInfo, JobStatus, QueueBackend

logger = logging.getLogger(__name__)

# Auto-cleanup completed/failed jobs older than this (seconds)
_JOB_RETENTION_SECONDS = 24 * 60 * 60  # 24 hours

# Run cleanup every N enqueue calls
_CLEANUP_INTERVAL = 50


class MemoryJobQueue(QueueBackend):
    """QueueBackend implementation using ThreadPoolExecutor.

    This is the default fallback when Redis/RQ is not available.
    Jobs are executed in-process via a bounded thread pool.

    IMPORTANT: Jobs do NOT persist across restarts. Jobs in flight
    when the container stops are lost. This matches Sublarr's current
    behavior of using daemon threads for background work.

    Completed/failed job metadata is retained for 24 hours for status
    queries, then automatically cleaned up to prevent memory leaks.
    """

    def __init__(self, max_workers: int = 2):
        """Initialize with a bounded thread pool.

        Args:
            max_workers: Maximum number of concurrent worker threads.
        """
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        self._jobs: dict = {}  # job_id -> job metadata dict
        self._lock = threading.Lock()
        self._enqueue_count = 0

    def enqueue(self, func, *args, job_id: str = None, **kwargs) -> str:
        """Submit a function for execution in the thread pool.

        Args:
            func: The callable to execute.
            *args: Positional arguments.
            job_id: Optional custom job ID. Auto-generated (uuid[:8]) if not provided.
            **kwargs: Keyword arguments.

        Returns:
            The job ID.
        """
        if job_id is None:
            job_id = uuid.uuid4().hex[:8]

        now = datetime.now(UTC).isoformat()
        func_name = getattr(func, "__name__", str(func))

        with self._lock:
            self._jobs[job_id] = {
                "status": JobStatus.QUEUED,
                "func_name": func_name,
                "enqueued_at": now,
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
                "future": None,
            }

        # Submit to thread pool
        future = self._executor.submit(self._run_job, job_id, func, *args, **kwargs)
        future.add_done_callback(lambda f: self._on_complete(job_id, f))

        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["future"] = future

        logger.debug("Enqueued job %s: %s (memory queue)", job_id, func_name)

        # Periodic cleanup
        self._enqueue_count += 1
        if self._enqueue_count % _CLEANUP_INTERVAL == 0:
            self._cleanup_old_jobs()

        return job_id

    def _run_job(self, job_id: str, func, *args, **kwargs) -> Any:
        """Execute the job function, updating status to RUNNING.

        Args:
            job_id: The job ID for status tracking.
            func: The callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The result of func(*args, **kwargs).
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = JobStatus.RUNNING
                self._jobs[job_id]["started_at"] = now

        return func(*args, **kwargs)

    def _on_complete(self, job_id: str, future: Future) -> None:
        """Callback when a job future completes (success or failure).

        Args:
            job_id: The job ID.
            future: The completed Future.
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            if job_id not in self._jobs:
                return

            self._jobs[job_id]["completed_at"] = now

            exc = future.exception()
            if exc is not None:
                self._jobs[job_id]["status"] = JobStatus.FAILED
                self._jobs[job_id]["error"] = str(exc)
                logger.debug("Job %s failed: %s", job_id, exc)
            else:
                self._jobs[job_id]["status"] = JobStatus.COMPLETED
                self._jobs[job_id]["result"] = future.result()

    def get_job(self, job_id: str) -> JobInfo | None:
        """Get job status from the in-memory tracker.

        Args:
            job_id: The job ID to look up.

        Returns:
            JobInfo if found, None otherwise.
        """
        with self._lock:
            meta = self._jobs.get(job_id)
            if meta is None:
                return None

            return JobInfo(
                id=job_id,
                func_name=meta["func_name"],
                status=meta["status"],
                enqueued_at=meta["enqueued_at"],
                started_at=meta["started_at"],
                completed_at=meta["completed_at"],
                result=meta["result"],
                error=meta["error"],
            )

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job if it hasn't started yet.

        Args:
            job_id: The job ID to cancel.

        Returns:
            True if the job was successfully cancelled.
        """
        with self._lock:
            meta = self._jobs.get(job_id)
            if meta is None:
                return False

            future = meta.get("future")
            if future is not None and future.cancel():
                meta["status"] = JobStatus.CANCELLED
                meta["completed_at"] = datetime.now(UTC).isoformat()
                logger.debug("Cancelled job %s", job_id)
                return True

            # Can't cancel a running or completed job via Future.cancel()
            return False

    def get_queue_length(self) -> int:
        """Get number of queued (not yet started) jobs."""
        with self._lock:
            return sum(
                1 for meta in self._jobs.values()
                if meta["status"] == JobStatus.QUEUED
            )

    def get_active_jobs(self) -> list[JobInfo]:
        """Get currently running jobs."""
        with self._lock:
            results = []
            for job_id, meta in self._jobs.items():
                if meta["status"] == JobStatus.RUNNING:
                    results.append(JobInfo(
                        id=job_id,
                        func_name=meta["func_name"],
                        status=meta["status"],
                        enqueued_at=meta["enqueued_at"],
                        started_at=meta["started_at"],
                        completed_at=meta["completed_at"],
                        result=meta["result"],
                        error=meta["error"],
                    ))
            return results

    def get_failed_jobs(self, limit: int = 50) -> list[JobInfo]:
        """Get failed jobs.

        Args:
            limit: Maximum number to return.
        """
        with self._lock:
            results = []
            for job_id, meta in self._jobs.items():
                if meta["status"] == JobStatus.FAILED:
                    results.append(JobInfo(
                        id=job_id,
                        func_name=meta["func_name"],
                        status=meta["status"],
                        enqueued_at=meta["enqueued_at"],
                        started_at=meta["started_at"],
                        completed_at=meta["completed_at"],
                        result=meta["result"],
                        error=meta["error"],
                    ))
                    if len(results) >= limit:
                        break
            return results

    def clear_failed(self) -> int:
        """Remove all failed job entries.

        Returns:
            Number of failed jobs cleared.
        """
        with self._lock:
            failed_ids = [
                jid for jid, meta in self._jobs.items()
                if meta["status"] == JobStatus.FAILED
            ]
            for jid in failed_ids:
                del self._jobs[jid]

        if failed_ids:
            logger.info("Cleared %d failed jobs from memory queue", len(failed_ids))
        return len(failed_ids)

    def get_backend_info(self) -> dict:
        """Get memory queue status information.

        Returns:
            Dict with type, max_workers, active count, queued count, total tracked.
        """
        with self._lock:
            active = sum(1 for m in self._jobs.values() if m["status"] == JobStatus.RUNNING)
            queued = sum(1 for m in self._jobs.values() if m["status"] == JobStatus.QUEUED)
            total = len(self._jobs)

        return {
            "type": "memory",
            "max_workers": self._max_workers,
            "active": active,
            "queued": queued,
            "total_tracked": total,
            "note": "In-process queue; jobs do NOT persist across restarts",
        }

    def _cleanup_old_jobs(self) -> None:
        """Remove completed/failed job entries older than _JOB_RETENTION_SECONDS.

        Prevents unbounded memory growth from accumulating job metadata.
        Called periodically from enqueue().
        """
        cutoff = time.time() - _JOB_RETENTION_SECONDS
        with self._lock:
            old_ids = []
            for jid, meta in self._jobs.items():
                if meta["status"] in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                    completed_at = meta.get("completed_at")
                    if completed_at:
                        try:
                            # Parse ISO timestamp and compare
                            dt = datetime.fromisoformat(completed_at)
                            if dt.timestamp() < cutoff:
                                old_ids.append(jid)
                        except (ValueError, TypeError):
                            # If timestamp is unparseable, clean it up
                            old_ids.append(jid)
            for jid in old_ids:
                del self._jobs[jid]

        if old_ids:
            logger.debug("Cleaned up %d old job entries from memory queue", len(old_ids))
