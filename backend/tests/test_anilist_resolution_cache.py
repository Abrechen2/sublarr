"""Tests for the AniList client singleton and title-resolution TTL cache.

Covers:
- get_anilist_client() returning a process-wide singleton (so the 0.7s
  inter-request rate gap actually applies across resolutions).
- anidb_mapper.resolve_anidb_from_title() caching both hits and misses,
  with a short negative TTL (misses may be transient AniList failures).
- Thread-safety of AniListClient._query()'s rate-gap check + HTTP call.
"""

from unittest.mock import MagicMock, patch


def test_get_anilist_client_is_singleton():
    from metadata import anilist_client

    anilist_client._client_singleton = None  # reset between runs
    a = anilist_client.get_anilist_client()
    b = anilist_client.get_anilist_client()
    assert a is b, "per-call construction resets the rate limiter"


def test_resolve_anidb_from_title_caches_misses():
    import anidb_mapper

    anidb_mapper._title_res_cache.clear()
    fake = MagicMock()
    fake.search_anime.return_value = None  # AniList knows nothing

    with patch.object(anidb_mapper, "_get_client", return_value=fake):
        assert anidb_mapper.resolve_anidb_from_title("Totally Unknown Show") is None
        assert anidb_mapper.resolve_anidb_from_title("Totally Unknown Show") is None

    assert fake.search_anime.call_count == 1, "second miss must come from the cache"


def test_resolve_anidb_from_title_cache_expires():
    import anidb_mapper

    anidb_mapper._title_res_cache.clear()
    fake = MagicMock()
    fake.search_anime.return_value = None

    with patch.object(anidb_mapper, "_get_client", return_value=fake):
        anidb_mapper.resolve_anidb_from_title("Show X")
        key = next(iter(anidb_mapper._title_res_cache))
        ts, val = anidb_mapper._title_res_cache[key]
        # misses use the SHORT negative TTL
        anidb_mapper._title_res_cache[key] = (ts - anidb_mapper._TITLE_RES_NEG_TTL - 1, val)
        anidb_mapper.resolve_anidb_from_title("Show X")

    assert fake.search_anime.call_count == 2, "expired entry must re-query"


def test_anilist_query_rate_gap_is_thread_safe():
    """Two threads must not both pass the 0.7s gap check (check-then-act race)."""
    import threading

    from metadata.anilist_client import AniListClient

    client = AniListClient()
    stamps: list[float] = []

    def fake_post(url, json=None, timeout=None):
        import time as _t

        stamps.append(_t.monotonic())

        class _R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"data": {}}

        return _R()

    with patch.object(client.session, "post", side_effect=fake_post):
        threads = [threading.Thread(target=client._query, args=("query {}", {})) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(g >= 0.65 for g in gaps), f"requests not serialized, gaps={gaps}"
