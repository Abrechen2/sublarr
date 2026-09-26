"""``lookup_series`` / ``lookup_movie`` keep a 404 apart from an outage
(final review I4): the sweep may only treat a title as gone on a real 404."""

from unittest.mock import MagicMock

import pytest
import requests

from radarr_client import RadarrClient
from sonarr_client import SonarrClient


def _response(status, body=None, bad_json=False):
    resp = MagicMock()
    resp.status_code = status
    if bad_json:
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = body
    return resp


@pytest.fixture(params=["series", "movie"])
def lookup(request):
    if request.param == "series":
        client = SonarrClient("http://sonarr", "key")
        return client, client.lookup_series
    client = RadarrClient("http://radarr", "key")
    return client, client.lookup_movie


def test_found(lookup):
    client, fn = lookup
    client.session.get = MagicMock(return_value=_response(200, {"path": "/media/A"}))
    assert fn(7) == (200, {"path": "/media/A"})


def test_a_404_stays_a_404(lookup):
    client, fn = lookup
    client.session.get = MagicMock(return_value=_response(404))
    assert fn(7) == (404, None)


def test_a_500_is_not_a_404(lookup):
    client, fn = lookup
    client.session.get = MagicMock(return_value=_response(500))
    assert fn(7) == (500, None)


def test_a_connection_error_has_no_status(lookup):
    client, fn = lookup
    client.session.get = MagicMock(side_effect=requests.ConnectionError("down"))
    assert fn(7) == (None, None)


def test_a_timeout_has_no_status(lookup):
    client, fn = lookup
    client.session.get = MagicMock(side_effect=requests.Timeout("slow"))
    assert fn(7) == (None, None)


def test_bad_json_has_no_status(lookup):
    client, fn = lookup
    client.session.get = MagicMock(return_value=_response(200, bad_json=True))
    assert fn(7) == (None, None)


def test_one_request_no_retries(lookup):
    client, fn = lookup
    client.session.get = MagicMock(return_value=_response(404))
    fn(7)
    assert client.session.get.call_count == 1
