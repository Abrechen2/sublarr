"""#200 — show which providers actually contribute, and flag the ones that don't.

Answering "which of my 23 enabled providers are earning their place?" required
reading raw container logs and querying subtitle_downloads by hand. Six turned
out to be contributing nothing.

Contribution is deliberately NOT folded into health. A provider that answers,
returns candidates and simply never wins the ranking is working correctly — it
is just not earning its slot. Calling that unhealthy would be wrong, and would
put a red dot next to something that has nothing to fix.
"""

from providers.manager_status_mixin import _contribution


class TestContributionShare:
    def test_share_of_all_downloads(self):
        share, _ = _contribution(downloads=25, total_downloads=100, total_searches=500)
        assert share == 0.25

    def test_no_downloads_anywhere_is_not_a_division_by_zero(self):
        share, _ = _contribution(downloads=0, total_downloads=0, total_searches=500)
        assert share == 0.0

    def test_the_only_contributor_holds_the_whole_share(self):
        share, _ = _contribution(downloads=7, total_downloads=7, total_searches=9)
        assert share == 1.0


class TestEarnsItsPlace:
    def test_one_download_ever_is_enough(self):
        """A rarely-winning provider still earns its slot. The question is
        whether it contributes at all, not whether it contributes a lot."""
        _, earns = _contribution(downloads=1, total_downloads=5000, total_searches=9000)
        assert earns is True

    def test_searched_plenty_and_never_won(self):
        _, earns = _contribution(downloads=0, total_downloads=5000, total_searches=1666)
        assert earns is False

    def test_a_young_provider_is_not_judged_yet(self):
        """Tri-state on purpose: "no evidence yet" is not "not earning its
        place", and a provider added yesterday must not be flagged."""
        _, earns = _contribution(downloads=0, total_downloads=5000, total_searches=3)
        assert earns is None

    def test_never_searched_at_all_is_also_undecided(self):
        _, earns = _contribution(downloads=0, total_downloads=0, total_searches=0)
        assert earns is None


class TestPayloadCarriesContribution:
    def test_status_dict_exposes_both_fields(self, app_ctx):
        from providers import ProviderManager

        statuses = ProviderManager().get_provider_status()
        assert statuses
        for s in statuses:
            assert "contribution_share" in s, f"{s['name']} has no contribution_share"
            assert "earns_its_place" in s, f"{s['name']} has no earns_its_place"

    def test_shares_do_not_exceed_one_in_total(self, app_ctx):
        statuses = __import__("providers").ProviderManager().get_provider_status()
        total = sum(s["contribution_share"] for s in statuses)
        assert total <= 1.0000001, f"shares sum to {total}, which cannot be right"
