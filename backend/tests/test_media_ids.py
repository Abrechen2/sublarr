"""services.media_ids: a negative id is a standalone id (docs/specs/standalone-ids.md).

Positive ids keep their old meaning: the arr when its client is configured,
otherwise (legacy, <= 1.17.x clients) a standalone row id.
"""

from __future__ import annotations

import pytest


class _Client:
    pass


@pytest.fixture
def sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _Client())


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)


@pytest.fixture
def radarr(monkeypatch):
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: _Client())


@pytest.fixture
def no_radarr(monkeypatch):
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


def test_key_conversions():
    from services.media_ids import standalone_id_from, standalone_key

    assert standalone_key(7) == -7
    assert standalone_id_from(-7) == 7
    assert standalone_id_from(7) is None
    assert standalone_id_from(0) is None
    with pytest.raises(ValueError):
        standalone_key(0)


def test_negative_series_id_is_standalone_even_with_sonarr(sonarr):
    from services.media_ids import resolve_series_ref

    ref = resolve_series_ref(-4)
    assert ref.is_standalone and ref.id == 4 and ref.key == -4


def test_positive_series_id_with_sonarr_is_sonarr(sonarr):
    from services.media_ids import resolve_series_ref

    ref = resolve_series_ref(4)
    assert ref.kind == "sonarr" and ref.id == 4 and ref.key == 4


def test_positive_series_id_without_sonarr_is_legacy_standalone(no_sonarr):
    from services.media_ids import resolve_series_ref

    ref = resolve_series_ref(4)
    assert ref.is_standalone and ref.id == 4 and ref.key == -4


def test_movie_refs(radarr):
    from services.media_ids import resolve_movie_ref

    assert resolve_movie_ref(9).kind == "radarr"
    neg = resolve_movie_ref(-9)
    assert neg.is_standalone and neg.id == 9 and neg.key == -9


def test_legacy_movie_without_radarr(no_radarr):
    from services.media_ids import resolve_movie_ref

    ref = resolve_movie_ref(9)
    assert ref.is_standalone and ref.key == -9


def test_owner_keys_for_items():
    from services.media_ids import movie_key_for_item, series_key_for_item

    assert series_key_for_item({"sonarr_series_id": 3}) == 3
    assert series_key_for_item({"standalone_series_id": 3}) == -3
    assert series_key_for_item({"sonarr_series_id": 5, "standalone_series_id": 3}) == 5
    assert series_key_for_item({}) is None
    assert movie_key_for_item({"radarr_movie_id": 2}) == 2
    assert movie_key_for_item({"standalone_movie_id": 2}) == -2
    assert movie_key_for_item({"standalone_series_id": 2}) is None
    assert series_key_for_item(None) is None
