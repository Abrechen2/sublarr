"""Three providers were searching endpoints that no longer exist (GH #207).

Reproduced 2026-09-14 against the live sites:

    POST https://www.tvsubtitles.net/search.php   q=doctor who       404
    POST https://www.tvsubtitles.net/search1.php  qs=doctor who      200
    POST https://subf2m.co/subtitles/searchbytitle  query=...&l=     405
    GET  https://subf2m.co/subtitles/searchbytitle?query=...&l=      200

Each had run hundreds of searches without a single result. What hid it was
the reporting: a 404 from the provider's own search endpoint was recorded as
"no results", which reads like a provider that has nothing for this library
rather than one whose request never arrives. So the HTTP failure has to
surface as a failure too — a silent 404 is the bug behind the bug.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.base import SubtitleResult
from providers.subf2m import Subf2mProvider
from providers.tvsubtitles import TVSubtitlesProvider


def _session_recording(status_code=200, text=""):
    """A session that records the call and answers with a canned response."""
    session = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    session.get.return_value = response
    session.post.return_value = response
    return session


# ---------------------------------------------------------------------------
# tvsubtitles — search.php is gone; search1.php took over, under a new field
# ---------------------------------------------------------------------------


def test_tvsubtitles_searches_the_endpoint_that_still_exists():
    provider = TVSubtitlesProvider()
    provider.session = _session_recording()

    provider._find_show("doctor who")

    url = provider.session.post.call_args.args[0]
    assert url.endswith("/search1.php"), url


def test_tvsubtitles_sends_the_field_name_the_endpoint_expects():
    """search1.php reads ``qs``; the old ``q`` yields an empty result page."""
    provider = TVSubtitlesProvider()
    provider.session = _session_recording()

    provider._find_show("doctor who")

    assert provider.session.post.call_args.kwargs["data"] == {"qs": "doctor who"}


# ---------------------------------------------------------------------------
# subf2m — the search page answers GET, and refuses POST with 405
# ---------------------------------------------------------------------------


def test_subf2m_searches_with_a_get_because_post_is_refused():
    provider = Subf2mProvider()
    provider.session = _session_recording()

    provider._search_titles("doctor who")

    assert provider.session.post.call_count == 0, "POST is answered with 405"
    assert provider.session.get.call_count == 1


def test_subf2m_passes_the_query_as_url_parameters():
    provider = Subf2mProvider()
    provider.session = _session_recording()

    provider._search_titles("doctor who")

    assert provider.session.get.call_args.kwargs["params"] == {"query": "doctor who", "l": ""}


# ---------------------------------------------------------------------------
# A dead endpoint must not read as an empty library
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 405, 403, 500])
def test_tvsubtitles_raises_when_its_search_endpoint_answers_with_an_error(status):
    """Silence let 342 searches look like 'nothing found' instead of 'broken'."""
    from providers.base import ProviderError

    provider = TVSubtitlesProvider()
    provider.session = _session_recording(status_code=status)

    with pytest.raises(ProviderError):
        provider._find_show("doctor who")


@pytest.mark.parametrize("status", [404, 405, 403, 500])
def test_subf2m_raises_when_its_search_endpoint_answers_with_an_error(status):
    from providers.base import ProviderError

    provider = Subf2mProvider()
    provider.session = _session_recording(status_code=status)

    with pytest.raises(ProviderError):
        provider._search_titles("doctor who")


# ---------------------------------------------------------------------------
# The markup moved too — reaching the right endpoint is only half the fix
# ---------------------------------------------------------------------------

# Captured from the live search pages on 2026-09-14. Both sites still list the
# same links, but neither wraps them in the <ul> the selectors were written for:
# tvsubtitles dropped the ``ul#r`` container, subf2m switched ``ul.title`` to
# ``div.title``. Matching on the container alone found nothing on either.

TVSUBTITLES_SEARCH_HTML = """
<html><body><div>
  <a href="/tvshow-141.html">Doctor Who (2005-2022)</a>
  <a href="/tvshow-691.html">Doctor Who Confidential (2005-2013)</a>
</div></body></html>
"""

SUBF2M_SEARCH_HTML = """
<html><body>
  <div class="title"><a href="/subtitles/doctor-who-season-2-2023">Doctor Who - Season 2 (2023)</a></div>
  <div class="title"><a href="/subtitles/doctor-who-third-season">Doctor Who - Third Season (2007)</a></div>
</body></html>
"""


def test_tvsubtitles_finds_shows_in_the_markup_the_site_now_returns():
    provider = TVSubtitlesProvider()
    provider.session = _session_recording(text=TVSUBTITLES_SEARCH_HTML)

    show = provider._find_show("Doctor Who")

    assert show is not None, "the links are on the page — the selector missed them"
    assert show["id"] == "141"
    assert show["name"] == "Doctor Who (2005-2022)"


def test_subf2m_finds_titles_in_the_markup_the_site_now_returns():
    provider = Subf2mProvider()
    provider.session = _session_recording(text=SUBF2M_SEARCH_HTML)

    titles = provider._search_titles("Doctor Who")

    assert len(titles) == 2, "the links are on the page — the selector missed them"
    assert titles[0]["url"].endswith("/subtitles/doctor-who-season-2-2023")


# ---------------------------------------------------------------------------
# tvsubtitles also re-numbered its episode pages
# ---------------------------------------------------------------------------

# The old code addressed an episode directly as
# ``/episode-{show_id}-{season}x{episode}.html``. That 404s: episodes now carry
# an opaque internal id, reachable only through the season page. Captured from
# the live site 2026-09-14 (show 141, season 1).

TVSUBTITLES_SEASON_HTML = """
<html><body><table>
  <tr><td>1x01</td><td>Rose</td><td>7</td><td><a href="episode-8245.html">Rose</a></td></tr>
  <tr><td>1x02</td><td>The End of the World</td><td>7</td>
      <td><a href="episode-8246.html">The End of the World</a></td></tr>
</table></body></html>
"""

# Each subtitle entry is one <a>, and the language sits in a flag image inside it.
TVSUBTITLES_EPISODE_HTML = """
<html><body><div class="left_articles">
  <a href="/subtitle-10903.html"><img src="images/flags/en.gif">Doctor Who 1x01 HDTV</a>
  <a href="/subtitle-11875.html"><img src="images/flags/es.gif">Doctor Who 1x01 spanish</a>
  <a href="/subtitle-139378.html"><img src="images/flags/fr.gif">Doctor Who 1x01 french</a>
</div></body></html>
"""


def _season_then_episode_session():
    """First GET answers with the season page, the second with the episode page."""
    session = MagicMock()
    season, episode = MagicMock(), MagicMock()
    season.status_code = episode.status_code = 200
    season.text, episode.text = TVSUBTITLES_SEASON_HTML, TVSUBTITLES_EPISODE_HTML
    session.get.side_effect = [season, episode]
    return session


def test_tvsubtitles_reaches_an_episode_through_the_season_page():
    """The direct ``episode-{show}-{s}x{e}.html`` address is gone (404)."""
    provider = TVSubtitlesProvider()
    provider.session = _season_then_episode_session()

    provider._get_episode_subtitles("141", 1, 1, "en")

    first_url, second_url = (c.args[0] for c in provider.session.get.call_args_list)
    assert first_url.endswith("/tvshow-141-1.html"), first_url
    assert second_url.endswith("/episode-8245.html"), second_url


def test_tvsubtitles_keeps_only_the_requested_language():
    """The flag image inside each entry is the only language marker left."""
    provider = TVSubtitlesProvider()
    provider.session = _season_then_episode_session()

    entries = provider._get_episode_subtitles("141", 1, 1, "en")

    assert len(entries) == 1
    assert entries[0]["url"].endswith("/download-10903.html")


# ---------------------------------------------------------------------------
# tvsubtitles hides the file behind a JS interstitial
# ---------------------------------------------------------------------------

# ``download-{id}.html`` no longer serves the archive. It serves a page that
# assembles the real path from fragments and then navigates to it. Captured
# 2026-09-14 from download-10903.html; the reconstructed path resolved to a
# 13125-byte ZIP.

TVSUBTITLES_INTERSTITIAL_HTML = """
<center><div id="linkPlace"><b>Wait: <span id="timeNumer">0</span> sec ...</b></div></center>
<script type="text/javascript">
var timerFIG = 1;
function startTimer() {
    var s1= 'fil';
    var s2= 'es/D';
    var s3= 'oc';
    var s4= 'tor Who_1x01_en.zip';
    document.location = s1+s2+s3+s4;
}
</script>
"""


def test_tvsubtitles_resolves_the_archive_behind_the_wait_page():
    """Following download-{id}.html literally yields 859 bytes of HTML, not a subtitle."""
    provider = TVSubtitlesProvider()
    provider.session = _session_recording(text=TVSUBTITLES_INTERSTITIAL_HTML)

    url = provider._resolve_download_url("https://www.tvsubtitles.net/download-10903.html")

    assert url == "https://www.tvsubtitles.net/files/Doctor%20Who_1x01_en.zip"


def test_tvsubtitles_reports_an_unreadable_wait_page_instead_of_guessing():
    provider = TVSubtitlesProvider()
    provider.session = _session_recording(text="<html><body>nothing here</body></html>")

    from providers.base import ProviderError

    with pytest.raises(ProviderError):
        provider._resolve_download_url("https://www.tvsubtitles.net/download-10903.html")


# ---------------------------------------------------------------------------
# subf2m hands the file off to its CDN
# ---------------------------------------------------------------------------


def test_subf2m_may_follow_its_download_redirect_to_its_own_cdn():
    """subf2m.co/subtitles/.../download 302s to isubcdn.com with a signed URL.

    Found by the P1 guard on a live download 2026-09-14: search returned 8
    results, and every one of them died at the redirect hop. The allowlist is
    per provider, so naming the CDN widens nothing but subf2m's own reach.
    """
    from security_utils import validate_download_url

    ok, err = validate_download_url(
        "https://isubcdn.com/subtitles/english/2026/154/22/doctor-who-english-589.zip"
        "?md5=LPRW-VHjLTDW9_6U8vDUpQ&expires=1789400598",
        "subf2m",
    )

    assert ok is True, err


def test_the_subf2m_cdn_stays_closed_to_other_providers():
    """A per-provider allowlist that leaks between providers is not an allowlist."""
    from security_utils import validate_download_url

    ok, _ = validate_download_url("https://isubcdn.com/subtitles/x.zip", "opensubtitles")

    assert ok is False


# ---------------------------------------------------------------------------
# The bundled Bazarr adapter hits the same dead URL — retire it
# ---------------------------------------------------------------------------


def test_the_subliminal_tvsubtitles_adapter_is_retired():
    """It POSTs to the same dead search.php and logged 98 HTTP 403s in 24 h.

    The vendored copy is Bazarr's, not ours to repair here, and the native
    ``tvsubtitles`` provider now covers the same site end to end. Leaving both
    registered means one working provider and one that can only ever fail.
    """
    from providers.registry import _BUILTIN_PROVIDERS

    assert "subliminal_tvsubtitles" not in _BUILTIN_PROVIDERS


def test_the_native_tvsubtitles_provider_stays():
    from providers.registry import _BUILTIN_PROVIDERS

    assert "tvsubtitles" in _BUILTIN_PROVIDERS


def test_tvsubtitles_only_unwraps_the_wait_page_not_every_download_url():
    """The interstitial is ``download-{id}.html``; an archive URL is not one.

    A substring test on ``/download-`` also catches a direct archive link — a
    stored result, or a path that merely contains the word — and would run it
    through a parser that can only fail on it.
    """
    provider = TVSubtitlesProvider()
    provider.session = MagicMock()
    archive = "https://www.tvsubtitles.net/files/download-1.zip"

    with patch("providers.tvsubtitles._stream_download", return_value=b"PK\x03\x04") as dl:
        provider.download(
            SubtitleResult(
                provider_name="tvsubtitles",
                subtitle_id="1",
                language="de",
                download_url=archive,
            )
        )

    assert provider.session.get.call_count == 0, "no wait page to unwrap here"
    assert dl.call_args.args[1] == archive
