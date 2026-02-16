"""In-memory cache backend with TTL eviction.

Named sqlite_cache.py for historical reasons; contains MemoryCacheBackend
which uses an in-process dict as the fallback when Redis is unavailable.
Thread-safe via threading.Lock.
"""

import logging
import threading
import time
from typing import Optional

from cache import CacheBackend

logger = logging.getLogger(__name__)

# Evict expired entries every N accesses
_EVICTION_INTERVAL = 100


class MemoryCacheBackend(CacheBackend):
    """CacheBackend implementation using an in-process dict with TTL.

    This is the default fallback when Redis is not available. Values are
    stored as (value, expires_at) tuples where expires_at is a Unix
    timestamp (0 means no expiry).

    Thread-safe: all dict access is guarded by a threading.Lock.
    Periodic cleanup removes expired entries every _EVICTION_INTERVAL
    accesses to prevent unbounded memory growth.
    """

    def __init__(self):
        super().__init__()
        self._store: dict = {}  # key -> (value, expires_at)
        self._lock = threading.Lock()
        self._access_count: int = 0

    def _is_expired(self, expires_at: float) -> bool:
        """Check if an entry has expired."""
        return expires_at > 0 and time.time() > expires_at

    def _maybe_evict(self) -> None:
        """Periodically evict all expired entries.

        Called on every access; actually evicts every _EVICTION_INTERVAL
        accesses. Caller must NOT hold self._lock.
        """
        self._access_count += 1
        if self._access_count % _EVICTION_INTERVAL == 0:
            self._evict_expired()

    def _evict_expired(self) -> None:
        """Remove all expired entries from the store.

        Caller must NOT hold self._lock.
        """
        now = time.time()
        with self._lock:
            expired_keys = [
                k for k, (_, exp) in self._store.items()
                if exp > 0 and now > exp
            ]
            for k in expired_keys:
                del self._store[k]
        if expired_keys:
            logger.debug("Evicted %d expired cache entries", len(expired_keys))

    def get(self, key: str) -> Optional[str]:
        """Get cached value by key, returning None if expired or missing."""
        self._maybe_evict()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expires_at = entry
            if self._is_expired(expires_at):
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: str, ttl_seconds: int = 0) -> None:
        """Set value with optional TTL (seconds). 0 means no expiry."""
        expires_at = (time.time() + ttl_seconds) if ttl_seconds > 0 else 0.0
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            _, expires_at = entry
            if self._is_expired(expires_at):
                del self._store[key]
                return False
            return True

    def clear(self, prefix: str = "") -> int:
        """Clear keys matching prefix. Empty prefix clears all."""
        with self._lock:
            if not prefix:
                count = len(self._store)
                self._store.clear()
                return count
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    def get_stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            size = len(self._store)
        return {
            "backend": "memory",
            "hits": self._hits,
            "misses": self._misses,
            "size": size,
        }
