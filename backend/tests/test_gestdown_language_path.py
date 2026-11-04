"""Gestdown's subtitles/get path takes the language itself, not an Addic7ed id."""

from unittest.mock import MagicMock, patch

from providers.base import VideoQuery
from providers.gestdown import GestdownProvider


def test_the_language_code_goes_into_the_path():
    provider = GestdownProvider()
    provider.session = MagicMock()
    provider.session.get.return_value = MagicMock(status_code=404)
    query = VideoQuery(series_title="Severance", season=1, episode=1, languages=["de", "en"])
    with patch.object(GestdownProvider, "_find_show", return_value={"id": "1UxT0N"}):
        provider.search(query)
    urls = [c.args[0] for c in provider.session.get.call_args_list]
    # Live 2026-11-04: ".../1/1/1" answered 404, ".../1/1/en" the subtitles.
    assert urls[-2:] == [
        "https://api.gestdown.info/subtitles/get/1UxT0N/1/1/de",
        "https://api.gestdown.info/subtitles/get/1UxT0N/1/1/en",
    ]
