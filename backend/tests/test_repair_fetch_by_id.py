"""Repair re-downloads by stored ``subtitle_id`` — for every provider, not just OpenSubtitles.

OpenSubtitles downloads by file id, so the repair path handed the provider a bare
result carrying nothing but that id. AnimeTosho downloads from a URL, and a result
without one dies on arrival ("No download URL") — the AnimeTosho-sourced sidecars
could never be repaired, no matter whether the provider was enabled.

How a stored id turns back into something downloadable is provider knowledge, so
each provider answers it for itself.
"""

from unittest.mock import MagicMock, patch

import pytest

from providers.animetosho import ATTACH_BASE, AnimeToshoProvider
from providers.base import SubtitleProvider, SubtitleResult
from services.repair.runner import RepairCandidate, fetch_original

ORIGINAL = b"1\n00:00:01,000 --> 00:00:03,000\ndarf ich dich um eine Sache bitten?\n"


class _StubProvider(SubtitleProvider):
    name = "stub"

    def search(self, query):
        return []

    def download(self, result):
        return b""


def test_the_default_hook_downloads_by_id():
    """OpenSubtitles and friends resolve the id server-side — keep that contract."""
    result = _StubProvider().result_for_download("6827171", "de")

    assert result.subtitle_id == "6827171"
    assert result.language == "de"
    assert result.provider_data["file_id"] == "6827171"


def test_animetosho_rebuilds_its_download_url_from_the_subtitle_id():
    """``entry_id:attach_id`` is all the search stored — and all the URL needs."""
    result = AnimeToshoProvider().result_for_download("687242:2376990", "de")

    assert result.download_url == f"{ATTACH_BASE}/0024451e/2376990.xz"
    assert result.provider_data["is_xz"] is True


def test_a_malformed_animetosho_subtitle_id_is_rejected():
    """Better a loud error than a URL pointing at some other user's subtitle."""
    with pytest.raises(ValueError, match="subtitle_id"):
        AnimeToshoProvider().result_for_download("687242", "de")


def test_fetch_original_downloads_what_the_provider_rebuilt(app_ctx, tmp_path):
    """The runner must not assemble the result itself — it asks the provider."""
    downloaded = {}

    class _UrlProvider(_StubProvider):
        name = "urly"

        def result_for_download(self, subtitle_id, language=""):
            return SubtitleResult(
                provider_name=self.name,
                subtitle_id=subtitle_id,
                language=language,
                download_url=f"https://example.test/{subtitle_id}.srt",
            )

        def download(self, result):
            if not result.download_url:
                raise ValueError("No download URL")
            downloaded["url"] = result.download_url
            return ORIGINAL

    manager = MagicMock()
    manager.get_provider.return_value = _UrlProvider()
    candidate = RepairCandidate(
        file_path=str(tmp_path / "Show - S01E01.de.srt"),
        language="de",
        fmt="srt",
        original_hash="irrelevant-here",
        provider="urly",
        subtitle_id="42:7",
    )

    with patch("providers.get_provider_manager", return_value=manager):
        content = fetch_original(candidate)

    assert downloaded["url"] == "https://example.test/42:7.srt"
    assert b"um eine Sache" in content
