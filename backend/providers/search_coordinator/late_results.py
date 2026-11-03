"""Results a provider delivered after the search stopped waiting for it.

Prod 2026-11-03: AnimeTosho answered a cold season-batch search in 28 s; the
search gave up at 23 s and returned without it. The thread kept running and
its 12 results — the only English ASS for the episode — were thrown away.
The next search asked again, timed out again, and the automatic search and
the SRT->ASS upgrade never saw an ASS for that season.

A late answer is now kept: per query and provider, for ``TTL_S``. The next
search for the same query takes it instead of asking that provider again,
and the wanted items of the video lose their backoff so that next search
comes with the scheduler's next pass rather than days later.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

#: How long a late answer stands in for the provider. Listings change slowly;
#: the wanted scheduler's next pass must still find it.
TTL_S = 6 * 3600

_lock = threading.Lock()
_store: dict[tuple[str, str], tuple[float, list]] = {}


def put(query_key: str, provider_name: str, results: list) -> None:
    with _lock:
        now = time.monotonic()
        for key in [k for k, (expires, _r) in _store.items() if expires <= now]:
            del _store[key]
        _store[(query_key, provider_name)] = (now + TTL_S, list(results))


def take(query_key: str, provider_name: str) -> list | None:
    """The late answer for this query and provider, once; None if there is none."""
    with _lock:
        entry = _store.pop((query_key, provider_name), None)
    if entry is None or entry[0] <= time.monotonic():
        return None
    return entry[1]


def clear() -> None:
    with _lock:
        _store.clear()


def capture(future, query_key: str, provider_name: str, query, excluded: set | None) -> None:
    """Keep ``future``'s results when it finishes. Never raises."""
    app = None
    try:
        from flask import current_app

        app = current_app._get_current_object()
    except Exception:  # noqa: BLE001 — outside a Flask context: no backoff reset
        app = None

    def _done(fut) -> None:
        try:
            if fut.cancelled() or fut.exception() is not None:
                return
            results, elapsed_ms = fut.result()
            if excluded:
                results = [r for r in results if (r.language or "").strip().lower() not in excluded]
            put(query_key, provider_name, results)
            logger.info(
                "Kept %d late result(s) from %s (%.0f ms) for the next search",
                len(results),
                provider_name,
                elapsed_ms,
            )
            if results:
                _search_again_soon(app, query)
        except Exception as exc:  # noqa: BLE001 — a lost late answer is the old behaviour
            logger.debug("Late results from %s dropped: %s", provider_name, exc)

    try:
        future.add_done_callback(_done)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Late result capture skipped for %s: %s", provider_name, exc)


def _search_again_soon(app, query) -> None:
    """Clear the backoff of the video's wanted items so they are searched next pass."""
    video = getattr(query, "file_path", "") or ""
    if not video or app is None:
        return
    from services.suspect_sidecars import _clear_backoff

    with app.app_context():
        for language in getattr(query, "languages", None) or []:
            _clear_backoff(video, language)
