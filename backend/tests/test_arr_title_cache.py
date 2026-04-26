"""Tests for the in-memory Sonarr/Radarr title cache."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services import arr_title_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    arr_title_cache.invalidate()
    yield
    arr_title_cache.invalidate()


def test_get_sonarr_series_titles_no_instances_returns_empty():
    with patch.object(arr_title_cache, "get_sonarr_instances", return_value=[]):
        assert arr_title_cache.get_sonarr_series_titles() == {}


def test_get_sonarr_series_titles_aggregates_across_instances():
    fake_instances = [
        {"name": "A", "url": "http://a", "api_key": "k1"},
        {"name": "B", "url": "http://b", "api_key": "k2"},
    ]

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def _fake_get(url, headers, timeout):
        if url.startswith("http://a"):
            return _Resp([{"id": 1, "title": "Frieren"}, {"id": 2, "title": "Cowboy Bebop"}])
        return _Resp([{"id": 3, "title": "Akiba"}])

    with (
        patch.object(arr_title_cache, "get_sonarr_instances", return_value=fake_instances),
        patch.object(arr_title_cache.requests, "get", side_effect=_fake_get),
    ):
        titles = arr_title_cache.get_sonarr_series_titles()
    assert titles == {1: "Frieren", 2: "Cowboy Bebop", 3: "Akiba"}


def test_get_sonarr_series_titles_swallows_request_errors():
    fake_instances = [{"name": "A", "url": "http://a", "api_key": "k"}]

    def _fake_get(url, headers, timeout):
        raise arr_title_cache.requests.ConnectionError("nope")

    with (
        patch.object(arr_title_cache, "get_sonarr_instances", return_value=fake_instances),
        patch.object(arr_title_cache.requests, "get", side_effect=_fake_get),
    ):
        # Must not raise; returns empty dict.
        assert arr_title_cache.get_sonarr_series_titles() == {}


def test_get_sonarr_series_titles_uses_cache_on_repeat_calls():
    fake_instances = [{"name": "A", "url": "http://a", "api_key": "k"}]
    call_count = {"n": 0}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"id": 1, "title": "X"}]

    def _fake_get(url, headers, timeout):
        call_count["n"] += 1
        return _Resp()

    with (
        patch.object(arr_title_cache, "get_sonarr_instances", return_value=fake_instances),
        patch.object(arr_title_cache.requests, "get", side_effect=_fake_get),
    ):
        arr_title_cache.get_sonarr_series_titles()
        arr_title_cache.get_sonarr_series_titles()
        arr_title_cache.get_sonarr_series_titles()
    assert call_count["n"] == 1


def test_get_radarr_movie_titles_uses_movie_path():
    fake_instances = [{"name": "A", "url": "http://a", "api_key": "k"}]
    captured_url = {"u": ""}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    def _fake_get(url, headers, timeout):
        captured_url["u"] = url
        return _Resp()

    with (
        patch.object(arr_title_cache, "get_radarr_instances", return_value=fake_instances),
        patch.object(arr_title_cache.requests, "get", side_effect=_fake_get),
    ):
        arr_title_cache.get_radarr_movie_titles()
    assert captured_url["u"].endswith("/api/v3/movie")
