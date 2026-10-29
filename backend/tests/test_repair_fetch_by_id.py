"""Repair re-downloads by stored ``subtitle_id`` — for every provider, not just OpenSubtitles.

OpenSubtitles downloads by file id, so the repair path handed the provider a bare
result carrying nothing but that id. AnimeTosho downloads from a URL, and a result
without one dies on arrival ("No download URL") — the AnimeTosho-sourced sidecars
could never be repaired, no matter whether the provider was enabled.

How a stored id turns back into something downloadable is provider knowledge, so
each provider answers it for itself.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from providers.animetosho import ATTACH_BASE, AnimeToshoProvider
from providers.base import SubtitleProvider, SubtitleResult
from providers.download_ref import apply_download_ref, download_ref
from services.repair.runner import RepairCandidate, fetch_original

ORIGINAL = b"1\n00:00:01,000 --> 00:00:03,000\ndarf ich dich um eine Sache bitten?\n"


class _StubProvider(SubtitleProvider):
    name = "stub"
    redownload_by_id = True

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


# --- every other provider: the download details saved with the download --------


class _UrlOnlyProvider(SubtitleProvider):
    """Downloads from the search's URL and payload, like Subf2m or a hub bundle."""

    name = "urlonly"

    def search(self, query):
        return []

    def download(self, result):
        if not result.download_url:
            raise ValueError("No download URL")
        self.seen = (result.download_url, dict(result.provider_data))
        return ORIGINAL


def _candidate(tmp_path, **kw):
    base = dict(
        file_path=str(tmp_path / "Show - S01E01.de.srt"),
        language="de",
        fmt="srt",
        original_hash="irrelevant-here",
        provider="urlonly",
        subtitle_id="1580751",
    )
    base.update(kw)
    return RepairCandidate(**base)


def test_a_url_provider_without_saved_details_is_unavailable_not_an_error():
    """Saved before Sublarr kept the details: say so instead of a provider error."""
    with pytest.raises(LookupError, match="download details"):
        _UrlOnlyProvider().result_for_download("1580751", "de")


def test_fetch_original_uses_the_saved_download_details(app_ctx, tmp_path):
    provider = _UrlOnlyProvider()
    manager = MagicMock()
    manager.get_provider.return_value = provider
    ref = download_ref(
        SubtitleResult(
            provider_name="urlonly",
            subtitle_id="1580751",
            language="de",
            download_url="https://subf2m.co/subtitles/show/german/1580751/download",
            provider_data={"payload": {"page": "/x/1"}, "is_zip": True},
        )
    )
    with patch("providers.get_provider_manager", return_value=manager):
        content = fetch_original(_candidate(tmp_path, download_ref=json.dumps(ref)))

    assert b"um eine Sache" in content
    assert provider.seen == (
        "https://subf2m.co/subtitles/show/german/1580751/download",
        {"payload": {"page": "/x/1"}, "is_zip": True},
    )


def test_the_saved_details_win_over_a_rebuild_from_the_id():
    """Custom API: the search's own URL, not the configured template (codex review)."""
    result = SubtitleResult(
        provider_name="customapi",
        subtitle_id="1",
        language="en",
        download_url="https://api.test/template/1",
        provider_data={"k": 0, "keep": True},
    )
    apply_download_ref(result, {"url": "https://api.test/files/1.srt", "provider_data": {"k": 1}})
    assert result.download_url == "https://api.test/files/1.srt"
    assert result.provider_data == {"k": 1, "keep": True}


class TestDownloadRefKeepsNoSecrets:
    def test_keys_and_tokens_are_dropped_from_the_url(self):
        ref = download_ref(
            SubtitleResult(
                provider_name="p",
                subtitle_id="1",
                language="de",
                download_url="https://h.test/dl?id=7&api_key=SECRET&token=T&x=1",
            )
        )
        assert ref["url"] == "https://h.test/dl?id=7&x=1"

    def test_secret_fields_and_unserialisable_values_are_dropped(self):
        ref = download_ref(
            SubtitleResult(
                provider_name="p",
                subtitle_id="1",
                language="de",
                provider_data={
                    "payload": {"url": "/s/1", "cookie": "c", "auth_token": "t"},
                    "page": "https://h.test/p?apikey=K&p=2",
                    "password": "p",
                    "subliminal_subtitle": object(),
                    "season": 2,
                },
            )
        )
        assert ref["provider_data"] == {
            "payload": {"url": "/s/1"},
            "page": "https://h.test/p?p=2",
            "season": 2,
        }

    def test_credentials_in_the_url_and_relative_urls_are_dropped(self):
        ref = download_ref(
            SubtitleResult(
                provider_name="p",
                subtitle_id="1",
                language="de",
                download_url="https://alice:secret@h.test/sub/42",
                provider_data={"payload": {"url": "/download/42?token=SECRET&n=1"}},
            )
        )
        assert ref["url"] == "https://h.test/sub/42"
        assert ref["provider_data"] == {"payload": {"url": "/download/42?n=1"}}

    def test_an_oversized_payload_is_not_kept(self):
        ref = download_ref(
            SubtitleResult(
                provider_name="p",
                subtitle_id="1",
                language="de",
                download_url="https://h.test/1",
                provider_data={"blob": "x" * 50_000},
            )
        )
        assert ref == {"url": "https://h.test/1"}

    def test_nothing_to_keep_is_none(self):
        assert (
            download_ref(SubtitleResult(provider_name="p", subtitle_id="1", language="de")) is None
        )
