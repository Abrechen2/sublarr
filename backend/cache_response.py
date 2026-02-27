"""Response caching for read-heavy GET endpoints.

Uses app.cache_backend to cache full JSON response body + status code
with a short TTL. Invalidate on config/profile changes via cache key prefix.
"""

import json
import logging
from functools import wraps

from flask import Response, current_app, request

logger = logging.getLogger(__name__)

DEFAULT_TTL = 60  # seconds


def cached_get(ttl_seconds: int = DEFAULT_TTL, key_prefix: str = "response:get:"):
    """Decorator: cache GET response in app.cache_backend.

    Only applies to GET. Cache key is key_prefix + request.path + '?' + query_string.
    Cached value is JSON: {"status": int, "body": str}.
    """

    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if request.method != "GET":
                return f(*args, **kwargs)

            cache = getattr(current_app, "cache_backend", None)
            if cache is None:
                return f(*args, **kwargs)

            key = key_prefix + request.path
            if request.query_string:
                key += "?" + request.query_string.decode("utf-8", errors="replace")

            try:
                raw = cache.get(key)
            except Exception as e:
                logger.debug("Response cache get failed: %s", e)
                raw = None

            if raw is not None:
                try:
                    data = json.loads(raw)
                    return Response(
                        data["body"],
                        status=data.get("status", 200),
                        mimetype="application/json",
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

            result = f(*args, **kwargs)
            if isinstance(result, tuple):
                resp, status = result[0], result[1]
                headers = result[2] if len(result) > 2 else None
            else:
                resp = result
                status = 200
                headers = None

            try:
                body = resp.get_data(as_text=True) if hasattr(resp, "get_data") else None
                if body is not None:
                    cache.set(
                        key,
                        json.dumps({"status": status, "body": body}),
                        ttl_seconds=ttl_seconds,
                    )
            except Exception as e:
                logger.debug("Response cache set failed: %s", e)

            if headers:
                return resp, status, headers
            return resp, status

        return inner

    return decorator


def invalidate_response_cache():
    """Clear all cached GET responses (call after config or profile changes)."""
    cache = getattr(current_app, "cache_backend", None)
    if cache is None:
        return
    try:
        n = cache.clear(prefix="response:get:")
        if n:
            logger.debug("Invalidated %d response cache entries", n)
    except Exception as e:
        logger.debug("Response cache invalidation failed: %s", e)
