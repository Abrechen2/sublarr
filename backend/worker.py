"""RQ worker entry point for Sublarr background jobs.

Start this process alongside the main Flask app to enable persistent,
Redis-backed job queuing. Each job runs inside a Flask application context
so that db.session, config, and all Flask extensions are available.

Usage:
    python worker.py

Configuration via environment variables (same as the main app):
    SUBLARR_REDIS_URL   Redis connection URL (required)
    SUBLARR_QUEUE_NAME  Queue name (default: sublarr)

Docker:
    Use docker-compose.redis.yml which configures the rq-worker service.
    Scale workers with:
        docker compose -f docker-compose.redis.yml up -d --scale rq-worker=N
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class _AppContextWorker:
    """Mixin that pushes a Flask app context around every RQ job.

    Defined at module level so it is picklable (required by RQ).
    """

    _app = None

    @classmethod
    def set_app(cls, app):
        cls._app = app

    def perform_job(self, job, queue, *args, **kwargs):
        if self._app is not None:
            with self._app.app_context():
                return super().perform_job(job, queue, *args, **kwargs)
        return super().perform_job(job, queue, *args, **kwargs)


def main():
    from app import create_app

    try:
        from redis import Redis
        from rq import Queue, Worker
    except ImportError as exc:
        logger.error("redis and rq packages are required: %s", exc)
        sys.exit(1)

    redis_url = os.environ.get("SUBLARR_REDIS_URL", "")
    if not redis_url:
        # Fall back to Pydantic settings so the same env var works
        try:
            from config import get_settings

            redis_url = get_settings().redis_url
        except Exception:
            pass

    if not redis_url:
        logger.error(
            "SUBLARR_REDIS_URL is not set. Set it to a Redis connection URL, "
            "e.g. redis://localhost:6379/0"
        )
        sys.exit(1)

    queue_name = os.environ.get("SUBLARR_QUEUE_NAME", "sublarr")

    app = create_app()

    try:
        redis_conn = Redis.from_url(redis_url, socket_connect_timeout=10)
        redis_conn.ping()
    except Exception as exc:
        logger.error("Cannot connect to Redis at %s: %s", redis_url, exc)
        sys.exit(1)

    # Build a Worker subclass with app context support
    class AppContextWorker(_AppContextWorker, Worker):
        pass

    AppContextWorker.set_app(app)

    queues = [Queue(queue_name, connection=redis_conn)]
    worker = AppContextWorker(queues, connection=redis_conn)

    logger.info("Sublarr RQ worker started — queue=%s  redis=%s", queue_name, redis_url)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
