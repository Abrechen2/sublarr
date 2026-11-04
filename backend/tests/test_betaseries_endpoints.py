"""BetaSeries: subtitles per episode id; /subtitles/show/<id> and /subtitles/movie are 404."""

from unittest.mock import MagicMock

from providers.base import VideoQuery
from providers.betaseries import BetaSeriesProvider


def _response(payload):
    return MagicMock(status_code=200, json=MagicMock(return_value=payload))


def _provider(*responses):
    provider = BetaSeriesProvider(api_key="k")
    provider.session = MagicMock()
    provider.session.get.side_effect = list(responses)
    return provider


def test_an_episode_is_looked_up_then_its_subtitles():
    provider = _provider(
        _response({"shows": [{"id": 1161}]}),
        _response({"episode": {"id": 4242}}),
        _response(
            {
                "subtitles": [
                    {
                        "id": 7,
                        "language": "VF",
                        "url": "https://www.betaseries.com/srt/7",
                        "source": "addic7ed",
                    },
                    {"id": 8, "language": "VO", "url": "https://www.betaseries.com/srt/8"},
                ]
            }
        ),
    )
    results = provider.search(
        VideoQuery(series_title="Lupin", season=1, episode=2, languages=["fr"])
    )
    calls = [(c.args[0], c.kwargs.get("params")) for c in provider.session.get.call_args_list]
    assert calls[1] == (
        "https://api.betaseries.com/episodes/search",
        {"show_id": "1161", "number": "S01E02"},
    )
    assert calls[2] == ("https://api.betaseries.com/subtitles/episode", {"id": "4242"})
    assert [(r.subtitle_id, r.language) for r in results] == [("7", "fr")]


def test_movies_are_not_searched():
    provider = _provider()
    assert provider.search(VideoQuery(title="Amelie", languages=["fr"])) == []
    provider.session.get.assert_not_called()
