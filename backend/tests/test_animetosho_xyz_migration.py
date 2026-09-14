"""AnimeTosho moved: animetosho.org froze, animetosho.xyz carries the live index.

Measured 2026-09-14: the newest entry on ``feed.animetosho.org`` is dated
2026-05-09, while ``feed.animetosho.xyz`` was serving releases minutes old.
Anything published after May was unreachable through this provider (GH #208).

The successor is not a domain swap. Three things differ:

1. The attachment URL is no longer derivable from the attachment id. ``.org``
   sharded as ``/storage/attach/{id:08x}/{id}.xz``; ``.xyz`` serves
   ``storage.animetosho.xyz/attachments/10003/1f0e.xz`` for attachment
   3586174 and ``.../1f12.xz`` for 3586175 — a step of four for an id step of
   one. It has to be read from the response, which now carries a ``url``.
2. The attachment ``info`` block renamed its keys: ``codec`` -> ``format``,
   ``lang`` -> ``language_code``, ``name`` -> ``language``.
3. The payload lives on its own host, so the P1 allowlist needs it.

Both schemas are accepted — ``.org`` may come back, and the parser has no
reason to be brittle about which spelling it gets.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.animetosho import ATTACH_BASE, FEED_API, AnimeToshoProvider
from providers.base import SubtitleFormat, VideoQuery
from security_utils import validate_download_url

XYZ_STORAGE_URL = "https://storage.animetosho.xyz/attachments/10003/1f0e.xz"


def _xyz_attachment():
    """An attachment exactly as feed.animetosho.xyz returns it."""
    return {
        "id": 3586174,
        "type": "subtitle",
        "size": None,
        "url": XYZ_STORAGE_URL,
        "info": {
            "default": True,
            "forced": False,
            "format": "ASS",
            "language": "English",
            "language_code": "eng",
        },
    }


def _org_attachment():
    """An attachment as the frozen feed.animetosho.org still returns it."""
    return {
        "id": 2758355,
        "type": "subtitle",
        "size": 25534,
        "info": {
            "codec": "ASS",
            "lang": "eng",
            "name": "English",
            "default": 0,
            "enabled": 1,
            "forced": 0,
            "trackid": 4,
            "tracknum": 5,
        },
    }


def _provider_returning(attachment):
    """A provider whose detail call yields one file holding ``attachment``."""
    provider = AnimeToshoProvider()
    provider.session = MagicMock()
    detail = MagicMock()
    detail.status_code = 200
    detail.json.return_value = {"files": [{"filename": "ep01.mkv", "attachments": [attachment]}]}
    provider.session.get.return_value = detail
    return provider


def _entry():
    return {"id": 687355, "title": "[BlackRabbit] Frieren - S01E01 [Bluray-1080p]", "num_files": 28}


def _query():
    return VideoQuery(series_title="Frieren", episode=1, languages=["en"])


def test_the_search_feed_points_at_the_live_index():
    """Querying the frozen index returns nothing published after May 2026."""
    assert "animetosho.xyz" in FEED_API


def test_an_attachment_carrying_its_own_url_is_downloaded_from_there():
    """The .xyz sharding is not derivable from the id — it must be read, not built."""
    provider = _provider_returning(_xyz_attachment())

    results = provider._process_entry(_entry(), _query())

    assert len(results) == 1
    assert results[0].download_url == XYZ_STORAGE_URL


def test_the_renamed_attachment_info_keys_are_understood():
    """``format``/``language_code`` carry what ``codec``/``lang`` used to."""
    provider = _provider_returning(_xyz_attachment())

    results = provider._process_entry(_entry(), _query())

    assert len(results) == 1
    assert results[0].format == SubtitleFormat.ASS
    assert results[0].language == "en"


def test_the_legacy_attachment_schema_still_resolves():
    """Regression guard: .org's spelling and its derived URL keep working."""
    provider = _provider_returning(_org_attachment())

    results = provider._process_entry(_entry(), _query())

    assert len(results) == 1
    assert results[0].format == SubtitleFormat.ASS
    assert results[0].language == "en"
    assert results[0].download_url == f"{ATTACH_BASE}/002a16d3/2758355.xz"


def test_the_xyz_storage_host_is_on_the_download_allowlist():
    """P1 blocks any host it was not told about — the payload moved off the main domain."""
    ok, err = validate_download_url(XYZ_STORAGE_URL, "animetosho")

    assert ok is True, err


def test_the_xyz_main_domain_is_on_the_download_allowlist():
    ok, err = validate_download_url("https://animetosho.xyz/view/687355", "animetosho")

    assert ok is True, err


# ---------------------------------------------------------------------------
# Repair — a stored id no longer yields the URL on its own
# ---------------------------------------------------------------------------


def test_a_repair_asks_the_api_where_the_attachment_lives():
    """History stores ``entry_id:attach_id``; on .xyz that is not enough to
    rebuild the URL, so the detail call has to supply it."""
    provider = _provider_returning(_xyz_attachment())

    result = provider.result_for_download("687355:3586174", "en")

    assert result.download_url == XYZ_STORAGE_URL


def test_a_repair_falls_back_to_the_derived_url_without_a_session():
    """Regression guard: the .org derivation still answers when no API is reachable."""
    result = AnimeToshoProvider().result_for_download("687242:2376990", "de")

    assert result.download_url == f"{ATTACH_BASE}/0024451e/2376990.xz"
    assert result.provider_data["is_xz"] is True
