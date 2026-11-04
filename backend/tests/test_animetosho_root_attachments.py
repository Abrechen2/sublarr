"""Root-level AnimeTosho attachments need an exact torrent episode identity."""

from unittest.mock import MagicMock

from providers.animetosho import AnimeToshoProvider
from providers.base import SubtitleFormat, VideoQuery


def _query():
    return VideoQuery(series_title="Frieren", season=1, episode=1, languages=["en"])


def _entry(title="[Group] Frieren S01E01 [1080p]", num_files=1):
    return {"id": 687355, "title": title, "num_files": num_files}


def _attachment():
    return {
        "id": 3586174,
        "type": "subtitle",
        "url": "https://storage.animetosho.xyz/attachments/10003/1f0e.xz",
        "info": {"format": "ASS", "language": "English", "language_code": "eng"},
    }


def _provider(detail):
    provider = AnimeToshoProvider()
    provider._fetch_torrent_detail = MagicMock(return_value=detail)
    return provider


def test_root_attachments_are_used_when_torrent_title_proves_episode():
    title = "[Group] Frieren S01E01 [1080p]"
    provider = _provider({"title": title, "attachments": [_attachment()]})

    results = provider._process_entry(_entry(title), _query())

    assert len(results) == 1
    assert results[0].format == SubtitleFormat.ASS
    assert results[0].language == "en"
    assert results[0].download_url == _attachment()["url"]


def test_root_attachments_are_skipped_when_torrent_title_is_a_pack():
    title = "[Group] Frieren S01E01-E12 Complete Season [1080p]"
    provider = _provider({"title": title, "attachments": [_attachment()]})

    results = provider._process_entry(_entry(title, num_files=12), _query())

    assert results == []
