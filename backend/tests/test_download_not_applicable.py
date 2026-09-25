"""A result the provider cannot serve is a skip, not a provider failure.

SubDL (#212): a season pack that does not contain the requested episode is
found only after it is downloaded. Raising a plain error there counted against
SubDL's circuit breaker and stats, so a few such packs in a row could switch a
healthy provider off.
"""

from unittest.mock import MagicMock

import pytest

from providers.base import ProviderNotApplicableError
from providers.download_manager import download_subtitle, search_and_download_best


def _result(provider_name="subdl", subtitle_id="s1", score=90):
    return MagicMock(provider_name=provider_name, subtitle_id=subtitle_id, score=score)


def test_download_passes_the_skip_on_without_tripping_the_breaker():
    provider = MagicMock()
    provider.download.side_effect = ProviderNotApplicableError("pack lacks E03")
    breaker = MagicMock()
    breaker.allow_request.return_value = True

    with pytest.raises(ProviderNotApplicableError):
        download_subtitle(
            {"subdl": provider}, {"subdl": breaker}, lambda _n: True, _result(), raise_skips=True
        )
    breaker.record_failure.assert_not_called()


def test_best_of_moves_on_without_a_stats_failure():
    first, second = _result(subtitle_id="pack"), _result(subtitle_id="single")

    def download(result):
        if result.subtitle_id == "pack":
            raise ProviderNotApplicableError("pack lacks E03")
        return b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"

    stats = MagicMock()
    chosen = search_and_download_best(
        lambda *a, **kw: [first, second], download, stats, query=MagicMock()
    )

    assert chosen is second
    assert all(c.kwargs.get("success") for c in stats.call_args_list), stats.call_args_list
