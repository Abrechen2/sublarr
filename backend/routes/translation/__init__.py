"""Translation admin API blueprint package."""

from routes.translation.concurrency import bp as concurrency_bp
from routes.translation.events import bp as events_bp
from routes.translation.queue import bp as queue_bp

__all__ = ["concurrency_bp", "events_bp", "queue_bp"]
