"""Settings pages fire /scoring/* GETs on every open; each was an uncached ORM
query. 60s response cache + explicit invalidation on every write route.

Asserts against app.cache_backend directly — implementation-agnostic w.r.t.
how the route fetches its data. Key format: cache_response.py:35.
"""

_KEY = "response:get:/api/v1/scoring/weights"


def test_scoring_weights_get_is_cached(client):
    resp = client.get("/api/v1/scoring/weights")
    assert resp.status_code == 200
    cache = client.application.cache_backend
    assert cache.get(_KEY) is not None, "GET must populate the response cache"


def test_scoring_weights_put_invalidates_cache(client):
    client.get("/api/v1/scoring/weights")
    cache = client.application.cache_backend
    assert cache.get(_KEY) is not None

    # The route only processes nested "episode"/"movie" dicts
    # (routes/hooks/scoring.py:103-106) — a top-level key would be silently
    # ignored and turn this test into a false positive.
    put = client.put("/api/v1/scoring/weights", json={"episode": {"hash_match": 90}})
    assert put.status_code == 200
    assert cache.get(_KEY) is None, "PUT must invalidate the cached GET response"
