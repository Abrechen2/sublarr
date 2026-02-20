"""Redis-backed cache implementation.

Uses a 'sublarr:' key prefix for namespace isolation when sharing a Redis
instance with other applications.
"""

import logging
from typing import Dict, Optional

from cache import CacheBackend

logger = logging.getLogger(__name__)

# Namespace prefix for all Sublarr cache keys
_KEY_PREFIX = "sublarr:"

# Batch size for scan-based deletion
_SCAN_BATCH_SIZE = 500


class RedisCacheBackend(CacheBackend):
    """CacheBackend implementation using Redis.

    All keys are prefixed with 'sublarr:' for namespace isolation.
    Supports batch operations (mget/mset) for future bulk use.
    """

    def __init__(self, redis_client):
        """Initialize with an already-connected Redis client.

        Args:
            redis_client: A redis.Redis instance (decode_responses=True recommended).
        """
        super().__init__()
        self.redis = redis_client

    def _prefixed(self, key: str) -> str:
        """Add namespace prefix to a key."""
        return f"{_KEY_PREFIX}{key}"

    def get(self, key: str) -> Optional[str]:
        """Get cached value by key."""
        value = self.redis.get(self._prefixed(key))
        if value is not None:
            self._hits += 1
            return value
        self._misses += 1
        return None

    def set(self, key: str, value: str, ttl_seconds: int = 0) -> None:
        """Set value with optional TTL."""
        prefixed = self._prefixed(key)
        if ttl_seconds > 0:
            self.redis.setex(prefixed, ttl_seconds, value)
        else:
            self.redis.set(prefixed, value)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        return bool(self.redis.delete(self._prefixed(key)))

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return bool(self.redis.exists(self._prefixed(key)))

    def clear(self, prefix: str = "") -> int:
        """Clear keys matching prefix using SCAN (non-blocking).

        Args:
            prefix: Additional prefix to match after the namespace prefix.
                    Empty string clears all Sublarr keys.

        Returns:
            Number of keys deleted.
        """
        pattern = f"{_KEY_PREFIX}{prefix}*"
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(
                cursor=cursor, match=pattern, count=_SCAN_BATCH_SIZE
            )
            if keys:
                deleted += self.redis.delete(*keys)
            if cursor == 0:
                break
        return deleted

    def get_stats(self) -> dict:
        """Return cache statistics including Redis server info."""
        stats = {
            "backend": "redis",
            "hits": self._hits,
            "misses": self._misses,
            "size": 0,
        }

        try:
            # Count Sublarr keys
            count = 0
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(
                    cursor=cursor, match=f"{_KEY_PREFIX}*", count=_SCAN_BATCH_SIZE
                )
                count += len(keys)
                if cursor == 0:
                    break
            stats["size"] = count

            # Add Redis server info
            info = self.redis.info("stats")
            stats["used_memory"] = info.get("used_memory_human", "unknown")
            stats["connected_clients"] = info.get("connected_clients", 0)
        except Exception as e:
            logger.debug("Could not fetch Redis stats: %s", e)

        return stats

    # ---- Batch operations ----

    def mget(self, keys: list) -> Dict[str, Optional[str]]:
        """Get multiple keys at once using Redis MGET.

        Args:
            keys: List of cache keys (without prefix).

        Returns:
            Dict mapping each key to its value (or None if missing).
        """
        if not keys:
            return {}
        prefixed = [self._prefixed(k) for k in keys]
        values = self.redis.mget(prefixed)
        result = {}
        for key, value in zip(keys, values):
            if value is not None:
                self._hits += 1
            else:
                self._misses += 1
            result[key] = value
        return result

    def mset(self, mapping: dict, ttl_seconds: int = 0) -> None:
        """Set multiple keys at once using a Redis pipeline.

        Args:
            mapping: Dict of key -> value pairs (without prefix).
            ttl_seconds: TTL for all keys. 0 means no expiry.
        """
        if not mapping:
            return
        pipe = self.redis.pipeline()
        for key, value in mapping.items():
            prefixed = self._prefixed(key)
            if ttl_seconds > 0:
                pipe.setex(prefixed, ttl_seconds, value)
            else:
                pipe.set(prefixed, value)
        pipe.execute()
