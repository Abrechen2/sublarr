"""The provider test probe must ask the question the real search asks.

Reported in #185 and re-stated twice since: the probe built its own thin query
from title/season/episode, while AnimeTosho and its class match through an
AniDB id the *real* pipeline resolves first. On the reference instance the
button found 0 results for a series the scheduler's own search found 18 for, so
a no-result outcome told the operator nothing about the download path — the one
thing the button exists to prove.

The fix is to stop building a second query: `build_query_from_wanted` is what
the search pipeline itself calls, AniDB resolution and all.
"""

from unittest.mock import MagicMock, patch

from providers.base import VideoQuery


class TestProbeQueryComesFromTheRealBuilder:
    def test_probe_carries_the_anidb_id_the_real_pipeline_resolves(self):
        """The whole point: a thin query cannot reach an AniDB-matching
        provider, so the probe has to carry what the real search carries."""
        from routes.providers import management

        wanted_row = {
            "id": 1,
            "item_type": "episode",
            "file_path": "/media/Show/S01E03.mkv",
            "target_language": "de",
            "title": "Show — S01E03",
            "season_episode": "S01E03",
        }
        enriched = VideoQuery(
            file_path="/media/Show/S01E03.mkv",
            series_title="Show",
            season=1,
            episode=3,
            languages=["de"],
            anidb_id=4242,
            absolute_episode=15,
        )

        with (
            patch.object(management, "_first_wanted_row", return_value=wanted_row),
            patch.object(management, "build_query_from_wanted", return_value=enriched) as builder,
        ):
            query = management._probe_query_from_wanted()

        builder.assert_called_once_with(wanted_row)
        assert query is not None
        assert query.anidb_id == 4242, "the probe dropped the AniDB id again (#185)"
        assert query.absolute_episode == 15
        assert query.languages == ["de"]

    def test_no_wanted_items_means_no_probe(self):
        from routes.providers import management

        with patch.object(management, "_first_wanted_row", return_value=None):
            assert management._probe_query_from_wanted() is None

    def test_a_builder_failure_does_not_fail_the_test_button(self):
        """A probe that cannot be built is not a provider fault — the button
        must still report on auth and reachability."""
        from routes.providers import management

        with (
            patch.object(management, "_first_wanted_row", return_value={"id": 1}),
            patch.object(
                management, "build_query_from_wanted", side_effect=RuntimeError("no metadata")
            ),
        ):
            assert management._probe_query_from_wanted() is None

    def test_forced_only_items_do_not_leak_into_the_probe(self):
        """A forced-subtitle item would probe for forced tracks only and find
        nothing almost everywhere — a misleading no-result for the operator."""
        from routes.providers import management

        forced = VideoQuery(
            file_path="/media/Show/S01E03.mkv",
            series_title="Show",
            season=1,
            episode=3,
            languages=["de"],
        )
        forced.forced_only = True

        with (
            patch.object(management, "_first_wanted_row", return_value={"id": 1}),
            patch.object(management, "build_query_from_wanted", return_value=forced),
        ):
            query = management._probe_query_from_wanted()

        assert query is not None
        assert query.forced_only is False


def _post_test(client, body, *, probe=None, searched=None):
    """Drive POST /providers/test/animetosho and capture the query it searched."""
    from routes.providers import management

    provider = MagicMock()
    provider.session = object()
    provider.health_check.return_value = (True, "OK")
    provider.search.side_effect = lambda q: searched.append(q) or []

    manager = MagicMock()
    manager._providers = {"animetosho": provider}

    with (
        patch("providers.get_provider_manager", return_value=manager),
        patch.object(management, "_probe_query_from_wanted", return_value=probe),
    ):
        return client.post("/api/v1/providers/test/animetosho", json=body)


class TestTheEndpointSearchesWithTheEnrichedQuery:
    """The endpoint used to unpack the probe into a fresh VideoQuery, which
    threw the enrichment straight back out. What reaches provider.search()
    must be the object the builder produced."""

    def test_default_probe_reaches_the_provider_intact(self, client):
        enriched = VideoQuery(
            file_path="/media/Show/S01E03.mkv",
            series_title="Show",
            season=1,
            episode=3,
            languages=["de"],
            anidb_id=4242,
            absolute_episode=15,
        )
        searched: list[VideoQuery] = []

        resp = _post_test(client, {"test_search": True}, probe=enriched, searched=searched)

        assert resp.status_code == 200
        assert len(searched) == 1
        assert searched[0].anidb_id == 4242, (
            "the endpoint rebuilt a thin query and dropped the AniDB id (#185)"
        )
        assert searched[0].absolute_episode == 15

    def test_an_explicit_query_is_honoured_as_sent(self, client):
        """The probe is the default, not an override: a caller asking for a
        specific search gets exactly that, unenriched."""
        searched: list[VideoQuery] = []

        resp = _post_test(
            client,
            {
                "test_search": True,
                "query": {"series_title": "Other", "season": 2, "episode": 5, "language": "en"},
            },
            probe=VideoQuery(series_title="Show", anidb_id=4242, languages=["de"]),
            searched=searched,
        )

        assert resp.status_code == 200
        assert len(searched) == 1
        assert searched[0].series_title == "Other"
        assert searched[0].anidb_id is None
        assert searched[0].languages == ["en"]

    def test_no_wanted_items_still_answers_instead_of_500ing(self, client):
        """An empty wanted list is not a provider fault — health and auth must
        still be reported."""
        searched: list[VideoQuery] = []

        resp = _post_test(client, {"test_search": True}, probe=None, searched=searched)

        assert resp.status_code == 200
        assert resp.get_json()["health_check"]["healthy"] is True
