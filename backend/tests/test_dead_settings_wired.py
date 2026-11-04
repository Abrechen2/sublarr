"""Settings the UI offers change behaviour (audit #61 A12-A19, A36).

Each test saves the setting the way the UI does and checks the consumer.
"""

from unittest.mock import MagicMock, patch


def test_the_metadata_cache_ttl_is_the_configured_one():
    from metadata import MetadataResolver

    resolver = MetadataResolver.__new__(MetadataResolver)
    with (
        patch("config.get_settings", return_value=MagicMock(metadata_cache_ttl_days=7)),
        patch("db.standalone.cache_metadata") as cache,
    ):
        resolver._set_cached("k", {"metadata_source": "tmdb", "title": "X"})

    assert cache.call_args.kwargs["ttl_days"] == 7


def test_gestdown_waits_the_configured_retry_delay():
    from providers.base import VideoQuery
    from providers.gestdown import GestdownProvider

    provider = GestdownProvider()
    provider.session = MagicMock()
    provider.session.get.side_effect = [MagicMock(status_code=423), MagicMock(status_code=404)]
    query = VideoQuery(series_title="Show", season=1, episode=2, languages=["en"])
    with (
        patch.object(GestdownProvider, "_find_show", return_value={"id": "s1"}),
        patch("config.get_settings", return_value=MagicMock(gestdown_retry_delay_s=2.5)),
        patch("providers.gestdown.time.sleep") as sleep,
    ):
        provider.search(query)

    sleep.assert_called_once_with(2.5)


def test_an_unbounded_gestdown_delay_falls_back_to_one_second():
    from providers.base import VideoQuery
    from providers.gestdown import GestdownProvider

    provider = GestdownProvider()
    provider.session = MagicMock()
    provider.session.get.side_effect = [MagicMock(status_code=423), MagicMock(status_code=404)]
    query = VideoQuery(series_title="Show", season=1, episode=2, languages=["en"])
    with (
        patch.object(GestdownProvider, "_find_show", return_value={"id": "s1"}),
        patch("config.get_settings", return_value=MagicMock(gestdown_retry_delay_s=float("inf"))),
        patch("providers.gestdown.time.sleep") as sleep,
    ):
        provider.search(query)

    sleep.assert_called_once_with(1.0)
