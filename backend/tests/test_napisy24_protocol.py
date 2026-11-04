"""Napisy24's CheckSub protocol (https://forum.napisy24.pl/viewtopic.php?t=142)."""

import io
import zipfile
from unittest.mock import MagicMock

import pytest

from providers.base import ProviderError, SubtitleFormat
from providers.napisy24 import Napisy24Provider

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nCzesc\n"


def _zip(**files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name.replace("_dot_", "."), data)
    return buf.getvalue()


def _answer(status=b"OK-2", payload=b""):
    return status + b"|res:1920x1080|fps:23.976|imdb:tt0460681|napisId:4711|tlPrc:100||" + payload


def _provider(content):
    provider = Napisy24Provider()
    provider.session = MagicMock()
    provider.session.post.return_value = MagicMock(status_code=200, content=content)
    return provider


REQUEST = {"fs": "2678822514", "fh": "A74C3D905E7D8A59", "md": "abc", "fn": "x.avi"}


def test_ok_2_carries_the_subtitle_in_its_zip():
    [result] = _provider(_answer(payload=_zip(film_dot_srt=SRT)))._check_sub(REQUEST)
    assert result.content == SRT
    assert result.format == SubtitleFormat.SRT
    assert result.subtitle_id == "napisy24:4711"
    assert result.fps == pytest.approx(23.976)
    assert result.provider_data["request"] == REQUEST


@pytest.mark.parametrize("status", [b"OK-0", b"OK-1", b"OK-3"])
def test_other_answers_carry_no_subtitle(status):
    # Until 1.20.0 every OK-* answer became a result with an invented URL.
    assert _provider(_answer(status, b""))._check_sub(REQUEST) == []


def test_a_zip_with_only_an_advert_is_no_subtitle():
    assert _provider(_answer(payload=_zip(INFO_dot_txt=b"reklama")))._check_sub(REQUEST) == []


def test_the_search_sends_the_opensubtitles_hash_upper_case(tmp_path):
    video = tmp_path / "Film.mkv"
    video.write_bytes(b"\0" * (256 * 1024))
    provider = _provider(b"OK-0||")
    from providers.base import VideoQuery

    provider.search(VideoQuery(file_path=str(video), languages=["pl"]))
    sent = provider.session.post.call_args.kwargs["data"]
    assert sent["fh"] == sent["fh"].upper() and len(sent["fh"]) == 16
    assert sent["md"] == sent["md"].lower() and len(sent["md"]) == 32


def test_a_cached_result_asks_again_on_download():
    provider = _provider(_answer(payload=_zip(film_dot_srt=SRT)))
    [result] = provider._check_sub(REQUEST)
    result.content = None  # the search cache keeps no content
    assert provider.download(result) == SRT


def test_download_without_content_or_request_fails_clearly():
    provider = _provider(b"OK-0||")
    [result] = _provider(_answer(payload=_zip(film_dot_srt=SRT)))._check_sub(REQUEST)
    result.content, result.provider_data = None, {}
    with pytest.raises(ProviderError):
        provider.download(result)
