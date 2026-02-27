"""Job queue abstraction layer with RQ and in-memory backends.

Package named 'job_queue' (not 'queue') to avoid shadowing Python's
stdlib queue module, which is used by concurrent.futures.

Provides a QueueBackend ABC with two implementations:
- RQJobQueue: Redis-backed persistent job queue via RQ
- MemoryJobQueue: In-process ThreadPoolExecutor fallback

Factory function auto-detects Redis/RQ availability and falls back gracefully.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Unified job status across all queue backends."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobInfo:
    """Unified job information across all queue backends."""

    id: str
    func_name: str
    status: JobStatus
    enqueued_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: Any | None = None
    error: str | None = None


class QueueBackend(ABC):
    """Abstract base class for job queue backends."""

    @abstractmethod
    def enqueue(self, func: Callable, *args, job_id: str = None, **kwargs) -> str:
        """Submit a function for background execution.

        Args:
            func: The callable to execute.
            *args: Positional arguments for the callable.
            job_id: Optional custom job ID. Auto-generated if not provided.
            **kwargs: Keyword arguments for the callable.

        Returns:
            The job ID (str).
        """

    @abstractmethod
    def get_job(self, job_id: str) -> JobInfo | None:
        """Get job status and metadata.

        Returns:
            JobInfo if found, None otherwise.
        """

    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending/queued job.

        Returns:
            True if the job was successfully cancelled.
        """

    @abstractmethod
    def get_queue_length(self) -> int:
        """Get number of pending (queued) jobs."""

    @abstractmethod
    def get_active_jobs(self) -> list[JobInfo]:
        """Get currently executing jobs."""

    @abstractmethod
    def get_failed_jobs(self, limit: int = 50) -> list[JobInfo]:
        """Get failed jobs.

        Args:
            limit: Maximum number of failed jobs to return.
        """

    @abstractmethod
    def clear_failed(self) -> int:
        """Clear all failed job records.

        Returns:
            Number of failed jobs cleared.
        """

    @abstractmethod
    def get_backend_info(self) -> dict:
        """Get backend type and status information.

        Returns:
            Dict with at least: type (str), plus backend-specific details.
        """


def create_job_queue(redis_url: str = "", queue_name: str = "sublarr") -> QueueBackend:
    """Factory function to create the appropriate job queue backend.

    If redis_url is provided, attempts to connect to Redis and import RQ.
    On any failure (missing packages, connection error), falls back to
    MemoryJobQueue with a log message.

    Args:
        redis_url: Redis connection URL. Empty string means use memory fallback.
        queue_name: Queue name for RQ (default: "sublarr").

    Returns:
        A QueueBackend instance (RQ or Memory).
    """
    if redis_url:
        try:
            import redis as redis_lib
        except ImportError:
            logger.info("redis package not installed, using memory job queue")
            from job_queue.memory_queue import MemoryJobQueue

            return MemoryJobQueue()

        try:
            import rq  # noqa: F401
        except ImportError:
            logger.info("rq package not installed, using memory job queue")
            from job_queue.memory_queue import MemoryJobQueue

            return MemoryJobQueue()

        try:
            client = redis_lib.Redis.from_url(
                redis_url,
                socket_connect_timeout=5,
            )
            client.ping()
            logger.info("RQ job queue connected: %s (queue: %s)", redis_url, queue_name)
            from job_queue.rq_queue import RQJobQueue

            return RQJobQueue(client, queue_name)
        except Exception as e:
            logger.warning("Redis unavailable for job queue (%s), using memory queue", e)

    from job_queue.memory_queue import MemoryJobQueue

    return MemoryJobQueue()
