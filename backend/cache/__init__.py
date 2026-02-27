"""Cache abstraction layer with Redis and in-memory backends.

Provides a CacheBackend ABC with two implementations:
- RedisCacheBackend: Redis-backed cache with namespace isolation
- MemoryCacheBackend: In-process dict with TTL eviction (fallback)

Factory function auto-detects Redis availability and falls back gracefully.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends.

    Tracks hit/miss statistics as instance attributes for monitoring.
    """

    def __init__(self):
        self._hits: int = 0
        self._misses: int = 0

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Get cached value by key.

        Returns:
            Cached string value, or None if not found / expired.
        """

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int = 0) -> None:
        """Set value with optional TTL.

        Args:
            key: Cache key.
            value: String value to cache.
            ttl_seconds: Time-to-live in seconds. 0 means no expiry.
        """

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key.

        Returns:
            True if the key existed and was deleted.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists (and is not expired)."""

    @abstractmethod
    def clear(self, prefix: str = "") -> int:
        """Clear all keys, or keys matching prefix.

        Returns:
            Number of keys deleted.
        """

    @abstractmethod
    def get_stats(self) -> dict:
        """Return cache statistics.

        Returns:
            Dict with at least: backend (str), hits (int), misses (int), size (int).
        """


def create_cache_backend(redis_url: str = "") -> CacheBackend:
    """Factory function to create the appropriate cache backend.

    If redis_url is provided, attempts to connect to Redis. On any failure
    (missing package, connection error, ping failure), falls back to
    MemoryCacheBackend with a log message.

    Args:
        redis_url: Redis connection URL (e.g. "redis://localhost:6379/0").
                   Empty string means use in-memory fallback.

    Returns:
        A CacheBackend instance (Redis or Memory).
    """
    if redis_url:
        try:
            import redis
        except ImportError:
            logger.info("redis package not installed, using memory cache")
            from cache.sqlite_cache import MemoryCacheBackend

            return MemoryCacheBackend()

        try:
            client = redis.Redis.from_url(
                redis_url,
                socket_connect_timeout=5,
                decode_responses=True,
            )
            client.ping()
            logger.info("Redis cache connected: %s", redis_url)
            from cache.redis_cache import RedisCacheBackend

            return RedisCacheBackend(client)
        except Exception as e:
            logger.warning("Redis unavailable (%s), using memory cache", e)

    from cache.sqlite_cache import MemoryCacheBackend

    return MemoryCacheBackend()
