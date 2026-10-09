"""My-Subs provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import html
import re
import time
import unicodedata
import urllib.parse
import urllib.request

PROVIDER_ID = "my_subs"
BASE_URL = "https://my-subs.co"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
HTTP_TIMEOUT_SECONDS = 15
MAX_CANDIDATES_PER_QUERY = 8


def _coerce_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        joined = " ".join(str(item) for item in value if item not in (None, ""))
        return joined or None
    return str(value)


def build_queries(video):
    video = video or {}
    kind = video.get("kind")
    if kind == "movie":
        title = (_coerce_text(video.get("title")) or "").strip()
        if not title:
            return []
        year = video.get("year")
        if year:
            return [f"{title} {year}", title]
        return [title]
    if kind == "episode":
        series = (_coerce_text(video.get("series")) or "").strip()
        season = video.get("season")
        episode = video.get("episode")
        if not series or season is None or episode is None:
            return []
        try:
            tag = f"S{int(season):02d}E{int(episode):02d}"
        except (TypeError, ValueError):
            return []
        return [series, f"{series} {tag}"]
    return []


_TAG_RE = re.compile(rb"<[^>]+>")
_WHITESPACE_BYTES_RE = re.compile(rb"\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_ANCHOR_RE = re.compile(rb"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S)
_HREF_RE = re.compile(rb"\bhref=(['\"])(?P<href>.*?)\1", re.I | re.S)
_TITLE_RE = re.compile(rb"\btitle=(['\"])(?P<title>.*?)\1", re.I | re.S)
_SHOW_RE = re.compile(r"^/showlistsubtitles-(?P<id>\d+)-(?P<slug>[^/?#]+)$")
_MOVIE_RE = re.compile(r"^/film-versions-(?P<id>\d+)-(?P<slug>[^/?#]+)-subtitles$")
_EPISODE_RE = re.compile(
    rb"href=(['\"])(?P<href>/versions-(?P<id>\d+)-(?P<episode>\d+)-(?P<season>\d+)-[^'\"]+)\1",
    re.I,
)
_EPISODE_VERSION_RE = re.compile(
    rb"<div class='(?P<class>version(?:-hearing)?)'><b>Version:</b>\s*"
    rb"<i>(?P<version>.*?)</i>(?P<suffix>.*?)</div>",
    re.I | re.S,
)
_LANG_RE = re.compile(
    rb'<span class="flag-icon flag-icon-(?P<flag>[^"]+)"\s+title="(?P<title>[^"]*)">'
    rb"</span>\s*(?:<i>(?P<label>.*?)</i>)?",
    re.I | re.S,
)
_DOWNLOAD_LINK_RE = re.compile(rb"href=(['\"])(?P<href>/downloads/[^'\"]+)\1", re.I)
_EPISODE_DOWNLOADS_RE = re.compile(rb"<b>Downloads\s*:</b>\s*(?P<count>\d+)", re.I)
_MOVIE_DOWNLOAD_RE = re.compile(
    rb"<a\b(?P<attrs>[^>]*\bhref=(['\"])/downloads/[^'\"]+\2[^>]*)"
    rb"[^>]*class=(['\"])[^'\"]*list-group-item[^'\"]*\3[^>]*>"
    rb"(?P<body>.*?)</a>",
    re.I | re.S,
)
_STRONG_RE = re.compile(rb"<strong>(?P<value>.*?)</strong>", re.I | re.S)
_PULL_DOWNLOADS_RE = re.compile(
    rb'<div class="pull-right"><b>(?P<count>\d+)</b>\s*'
    rb'<span class="glyphicon glyphicon-download-alt"></span></div>',
    re.I | re.S,
)
_REAL_URL_RE = re.compile(rb'REAL_URL\s*=\s*"(?P<url>(?:\\.|[^"])*)"', re.I)
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


def _decode(data):
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def _strip_tags(data):
    text = _TAG_RE.sub(b"", data or b"")
    text = _WHITESPACE_BYTES_RE.sub(b" ", text).strip()
    return html.unescape(_decode(text))


def _clean_text(value):
    return _WHITESPACE_RE.sub(" ", html.unescape(_decode(value))).strip()


def _normalize(text):
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", _coerce_text(text) or "")
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _normalize_tokens(text):
    return [token for token in _normalize(text).split(" ") if token]


def _release_tokens(text):
    return {token for token in re.split(r"[^A-Za-z0-9]+", str(text).lower()) if token}


def _multi_token_present(release_tokens, value):
    chunks = [chunk for chunk in re.split(r"[^A-Za-z0-9]+", str(value or "").lower()) if chunk]
    return bool(chunks) and all(chunk in release_tokens for chunk in chunks)


def _safe_path(path):
    return urllib.parse.quote(path, safe="/-_.~()%")


def _absolute_url(path):
    if not path:
        return None
    value = _decode(path).replace("\\/", "/")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"{BASE_URL}/{_safe_path(value.lstrip('/'))}"


def _href_from_attrs(attrs):
    match = _HREF_RE.search(attrs or b"")
    if not match:
        return ""
    return _decode(match.group("href"))


def _title_from_attrs(attrs):
    match = _TITLE_RE.search(attrs or b"")
    if not match:
        return ""
    return _clean_text(match.group("title"))


def parse_search_results(html_bytes):
    if not html_bytes:
        return []
    results = []
    seen = set()
    for anchor in _ANCHOR_RE.finditer(html_bytes):
        attrs = anchor.group("attrs")
        href = _href_from_attrs(attrs)
        show_match = _SHOW_RE.match(href)
        movie_match = _MOVIE_RE.match(href)
        if not show_match and not movie_match:
            continue

        body_text = _strip_tags(anchor.group("body"))
        title_attr = _title_from_attrs(attrs)
        raw_title = title_attr or body_text
        media_type = "episode" if show_match else "movie"
        match = show_match or movie_match
        key = (media_type, match.group("id"))
        if key in seen:
            continue
        seen.add(key)

        year = None
        title = raw_title.strip()
        if media_type == "movie":
            year_match = re.search(r"\((\d{4})\)", body_text)
            if year_match:
                year = int(year_match.group(1))
            title = re.sub(r"\s*\(\d{4}\)\s*$", "", body_text).strip() or title

        results.append(
            {
                "media_type": media_type,
                "provider_id": match.group("id"),
                "slug": match.group("slug"),
                "title": title,
                "year": year,
                "detail_url": _absolute_url(href),
            }
        )
    return results


def find_episode_detail_url(html_bytes, season, episode):
    if not html_bytes:
        return None
    try:
        target_season = int(season)
        target_episode = int(episode)
    except (TypeError, ValueError):
        return None
    for match in _EPISODE_RE.finditer(html_bytes):
        if (
            int(match.group("season")) == target_season
            and int(match.group("episode")) == target_episode
        ):
            return _absolute_url(match.group("href"))
    return None


_LANGUAGE_NAME_TO_ALPHA2 = {
    "albanian": "sq",
    "arabic": "ar",
    "english": "en",
    "french": "fr",
    "spanish": "es",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "polish": "pl",
    "russian": "ru",
    "turkish": "tr",
    "hindi": "hi",
    "indonesian": "id",
    "dutch": "nl",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "czech": "cs",
    "greek": "el",
    "hungarian": "hu",
    "romanian": "ro",
    "bulgarian": "bg",
    "swedish": "sv",
    "danish": "da",
    "norwegian": "no",
    "finnish": "fi",
    "ukrainian": "uk",
    "slovak": "sk",
    "croatian": "hr",
    "serbian": "sr",
    "slovenian": "sl",
    "lithuanian": "lt",
    "latvian": "lv",
    "estonian": "et",
    "vietnamese": "vi",
    "thai": "th",
    "malay": "ms",
    "filipino": "tl",
    "tagalog": "tl",
    "hebrew": "he",
    "persian": "fa",
    "urdu": "ur",
    "bengali": "bn",
}
# Portuguese variants resolve to the same alpha2 but carry a country so that
# Brazilian Portuguese stays distinct (alpha3 "por" + country_alpha2 "BR").
_BRAZILIAN_PORTUGUESE_NAMES = frozenset(
    {
        "brazilian portuguese",
        "portuguese brazilian",
        "portuguese brazil",
        "portuguese br",
        "brazilian",
    }
)
_FLAG_TO_ALPHA2 = {
    "gb": "en",
    "uk": "en",
    "en": "en",
    "sa": "ar",
    "br": "pt",
    "pt": "pt",
    "cn": "zh",
    "jp": "ja",
    "kr": "ko",
    "gr": "el",
    "cz": "cs",
    "dk": "da",
    "se": "sv",
    "vn": "vi",
    "al": "sq",
    "ph": "tl",
}
_ALPHA3_TO_ALPHA2 = {
    "eng": "en",
    "spa": "es",
    "fra": "fr",
    "deu": "de",
    "ita": "it",
    "por": "pt",
    "pol": "pl",
    "rus": "ru",
    "tur": "tr",
    "ara": "ar",
    "hin": "hi",
    "ind": "id",
    "nld": "nl",
    "zho": "zh",
    "jpn": "ja",
    "kor": "ko",
    "ces": "cs",
    "ell": "el",
    "hun": "hu",
    "ron": "ro",
    "bul": "bg",
    "swe": "sv",
    "dan": "da",
    "nor": "no",
    "fin": "fi",
    "ukr": "uk",
    "slk": "sk",
    "hrv": "hr",
    "srp": "sr",
    "slv": "sl",
    "lit": "lt",
    "lav": "lv",
    "est": "et",
    "vie": "vi",
    "tha": "th",
    "msa": "ms",
    "fil": "tl",
    "heb": "he",
    "fas": "fa",
    "urd": "ur",
    "ben": "bn",
    "sqi": "sq",
}
_ALPHA2_TO_ALPHA3 = {value: key for key, value in _ALPHA3_TO_ALPHA2.items()}


def _language_code(flag, title, label=""):
    """Resolve a my-subs flag/title/label to an (alpha2, country) pair.

    The country is None for everything except Brazilian Portuguese, which keeps
    alpha2 "pt" but carries country "BR" so it does not collapse into generic
    Portuguese (alpha3 "por" + country_alpha2 "BR").
    """
    title_text = _normalize(title or label)
    cleaned = re.sub(r"\s+", " ", re.sub(r"[()]", " ", title_text)).strip()
    flag_code = (flag or "").lower().split("-", 1)[0]
    if title_text in _BRAZILIAN_PORTUGUESE_NAMES or cleaned in _BRAZILIAN_PORTUGUESE_NAMES:
        return "pt", "BR"
    if flag_code == "br":
        return "pt", "BR"
    if title_text in _LANGUAGE_NAME_TO_ALPHA2:
        return _LANGUAGE_NAME_TO_ALPHA2[title_text], None
    if cleaned in _LANGUAGE_NAME_TO_ALPHA2:
        return _LANGUAGE_NAME_TO_ALPHA2[cleaned], None
    alpha2 = _FLAG_TO_ALPHA2.get(flag_code, flag_code if len(flag_code) == 2 else None)
    return alpha2, None


def _requested_country(language):
    country = language.get("country_alpha2") or language.get("country")
    if isinstance(country, str) and country.strip():
        return country.strip().upper()
    return None


def _language_key_for(language):
    """Return the requested (alpha2, country) pair, or None when unresolvable."""
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    alpha2 = (language.get("alpha2") or "").lower()
    if not alpha2:
        alpha2 = _ALPHA3_TO_ALPHA2.get(alpha3, "")
    if not alpha2:
        return None
    country = _requested_country(language)
    # Only Portuguese carries a country distinction for this site (pt vs pt-BR).
    if alpha2 != "pt":
        country = None
    return alpha2, country


def _alpha3_for(alpha2):
    return _ALPHA2_TO_ALPHA3.get(alpha2)


def _candidate_matches_kind(candidate, kind):
    if kind == "movie":
        return candidate.get("media_type") == "movie"
    if kind == "episode":
        return candidate.get("media_type") == "episode"
    return False


def _downloads_count(pattern, data):
    match = pattern.search(data or b"")
    if not match:
        return 0
    return int(match.group("count"))


def _entry_from_parts(page_url, media_title, release, code, download_url, count, hi):
    alpha2, country = code
    alpha3 = _alpha3_for(alpha2)
    if not alpha3:
        return None
    release_info = release or media_title or ""
    return {
        "language_alpha2": alpha2,
        "language_alpha3": alpha3,
        "language_country": country,
        "release_info": release_info,
        "download_url": download_url,
        "downloads": count,
        "hearing_impaired": bool(hi),
        "page_url": page_url,
        "media_title": media_title,
    }


def _parse_episode_entries(html_bytes, page_url, media_title):
    entries = []
    for chunk in html_bytes.split(b'<div style="background-color: #f5f5f5;'):
        if b"/downloads/" not in chunk or b"class='version" not in chunk:
            continue
        version_match = _EPISODE_VERSION_RE.search(chunk)
        lang_match = _LANG_RE.search(chunk)
        download_match = _DOWNLOAD_LINK_RE.search(chunk)
        if not version_match or not lang_match or not download_match:
            continue
        release = _clean_text(version_match.group("version"))
        code = _language_code(
            _decode(lang_match.group("flag")),
            _decode(lang_match.group("title")),
            _strip_tags(lang_match.group("label") or b""),
        )
        if not code[0]:
            continue
        entry = _entry_from_parts(
            page_url,
            media_title,
            release,
            code,
            _absolute_url(download_match.group("href")),
            _downloads_count(_EPISODE_DOWNLOADS_RE, chunk),
            version_match.group("class").lower() == b"version-hearing"
            or b"Hearing Impaired" in version_match.group("suffix"),
        )
        if entry:
            entries.append(entry)
    return entries


def _parse_movie_entries(html_bytes, page_url, media_title):
    entries = []
    for match in _MOVIE_DOWNLOAD_RE.finditer(html_bytes):
        attrs = match.group("attrs")
        body = match.group("body")
        lang_match = _LANG_RE.search(body)
        release_match = _STRONG_RE.search(body)
        if not lang_match or not release_match:
            continue
        code = _language_code(
            _decode(lang_match.group("flag")),
            _decode(lang_match.group("title")),
            _strip_tags(lang_match.group("label") or b""),
        )
        if not code[0]:
            continue
        entry = _entry_from_parts(
            page_url,
            media_title,
            _strip_tags(release_match.group("value")),
            code,
            _absolute_url(_href_from_attrs(attrs)),
            _downloads_count(_PULL_DOWNLOADS_RE, body),
            False,
        )
        if entry:
            entries.append(entry)
    return entries


def parse_subtitle_entries(html_bytes, page_url, media_title):
    if not html_bytes:
        return []
    return _parse_episode_entries(html_bytes, page_url, media_title) + _parse_movie_entries(
        html_bytes,
        page_url,
        media_title,
    )


def _episode_tag_in(candidate_norm, season, episode):
    patterns = (
        rf"\bs0*{int(season)}e0*{int(episode)}\b",
        rf"\bseason\s*0*{int(season)}\s*episode\s*0*{int(episode)}\b",
    )
    return any(re.search(pattern, candidate_norm) for pattern in patterns)


def _season_in(candidate_norm, season):
    patterns = (
        rf"\bs0*{int(season)}(?=e|\W|$)",
        rf"\bseason\s*0*{int(season)}\b",
    )
    return any(re.search(pattern, candidate_norm) for pattern in patterns)


def compute_score(video, candidate_title):
    matches = derive_matches(video, candidate_title)
    kind = (video or {}).get("kind")
    if kind == "movie":
        if "title" in matches and "year" in matches:
            return 100
        if "title" in matches:
            return 90
        return 60
    if kind == "episode":
        if "series" in matches and "episode" in matches:
            return 95
        if "series" in matches:
            return 85
        return 60
    return 60


def derive_matches(video, candidate_title):
    if not video:
        return []
    candidate_norm = _normalize(candidate_title)
    candidate_tokens = set(_normalize_tokens(candidate_title))
    release_tokens = _release_tokens(candidate_title)
    matches = []
    kind = video.get("kind")
    if kind == "movie":
        title_tokens = _normalize_tokens(video.get("title"))
        if title_tokens and all(token in candidate_tokens for token in title_tokens):
            matches.append("title")
        year = video.get("year")
        if year and str(year) in candidate_tokens:
            matches.append("year")
    elif kind == "episode":
        series_tokens = _normalize_tokens(video.get("series"))
        if series_tokens and all(token in candidate_tokens for token in series_tokens):
            matches.append("series")
        try:
            season = int(video.get("season"))
            episode = int(video.get("episode"))
        except (TypeError, ValueError):
            season = episode = None
        if season is not None and _season_in(candidate_norm, season):
            matches.append("season")
        if (
            season is not None
            and episode is not None
            and _episode_tag_in(candidate_norm, season, episode)
        ):
            matches.append("episode")

    for key in ("source", "resolution", "video_codec", "audio_codec", "release_group"):
        value = _coerce_text(video.get(key))
        if value and _multi_token_present(release_tokens, value):
            matches.append(key)
    return matches


def extract_download_url(html_bytes, page_url):
    if not html_bytes:
        return None
    match = _REAL_URL_RE.search(html_bytes)
    if not match:
        return None
    raw = _decode(match.group("url")).replace("\\/", "/")
    return urllib.parse.urljoin(page_url or BASE_URL, raw)


def _looks_like_html(body):
    prefix = (body or b"")[:512].lstrip().lower()
    return (
        prefix.startswith(b"<!doctype")
        or prefix.startswith(b"<html")
        or prefix.startswith(b"<style")
        or b"<html" in prefix
    )


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


class MySubsProvider:
    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def search(self, video, languages, config):
        config = dict(config or {})
        requested_keys = {_language_key_for(lang) for lang in languages or []}
        requested_keys.discard(None)
        if not requested_keys:
            return []
        queries = build_queries(video)
        if not queries:
            return []

        results = []
        seen_payloads = set()
        for query in queries:
            search_url = f"{BASE_URL}/search.php?key={urllib.parse.quote(query, safe='')}"
            _sleep(config)
            search_html = self._http_get(search_url)
            candidates = [
                candidate
                for candidate in parse_search_results(search_html)
                if _candidate_matches_kind(candidate, video.get("kind"))
            ][:MAX_CANDIDATES_PER_QUERY]
            for candidate in candidates:
                detail_url = self._detail_url_for_candidate(candidate, video, config)
                if not detail_url:
                    continue
                _sleep(config)
                try:
                    detail_html = self._http_get(detail_url, referer=candidate["detail_url"])
                except Exception:
                    continue
                media_title = self._media_title(video, candidate)
                for entry in parse_subtitle_entries(detail_html, detail_url, media_title):
                    entry_key = (entry["language_alpha2"], entry.get("language_country"))
                    if entry_key not in requested_keys:
                        continue
                    payload_key = (
                        entry["download_url"],
                        entry["language_alpha3"],
                        entry.get("language_country"),
                    )
                    if payload_key in seen_payloads:
                        continue
                    seen_payloads.add(payload_key)
                    results.append(self._result_from_entry(video, entry))
            if results:
                break
        return results

    def _detail_url_for_candidate(self, candidate, video, config):
        kind = (video or {}).get("kind")
        if kind == "movie" and candidate.get("media_type") == "movie":
            return candidate["detail_url"]
        if kind == "episode" and candidate.get("media_type") == "episode":
            _sleep(config)
            try:
                show_html = self._http_get(candidate["detail_url"])
            except Exception:
                return None
            return find_episode_detail_url(
                show_html,
                video.get("season"),
                video.get("episode"),
            )
        return None

    def _media_title(self, video, candidate):
        kind = (video or {}).get("kind")
        if kind == "movie":
            title = candidate.get("title") or _coerce_text(video.get("title")) or ""
            year = candidate.get("year")
            return f"{title} ({year})" if year else title
        if kind == "episode":
            series = candidate.get("title") or _coerce_text(video.get("series")) or ""
            try:
                return f"{series} S{int(video.get('season')):02d}E{int(video.get('episode')):02d}"
            except (TypeError, ValueError):
                return series
        return candidate.get("title") or "My-Subs subtitle"

    def _result_from_entry(self, video, entry):
        candidate_title = f"{entry['media_title']} {entry['release_info']}"
        score = compute_score(video, candidate_title)
        alpha3 = entry["language_alpha3"]
        alpha2 = entry["language_alpha2"]
        country = entry.get("language_country")
        lang_suffix = f"{alpha3}-{country}" if country else alpha3
        file_lang = f"{alpha2}-{country.lower()}" if country else alpha2
        download_id = _hashlib.sha1(entry["download_url"].encode("utf-8")).hexdigest()[:16]
        language = {
            "alpha3": alpha3,
            "alpha2": alpha2,
            "hi": entry["hearing_impaired"],
            "forced": False,
        }
        if country:
            language["country_alpha2"] = country
        provider_payload = {
            "provider": PROVIDER_ID,
            "schema": 1,
            "download_url": entry["download_url"],
            "page_url": entry["page_url"],
            "language": alpha3,
            "release_info": entry["release_info"],
        }
        if country:
            provider_payload["country_alpha2"] = country
        return {
            "provider": PROVIDER_ID,
            "id": f"my-subs-{download_id}-{lang_suffix}",
            "language": language,
            "release_info": entry["release_info"],
            "filename": f"my-subs.{download_id}.{file_lang}.srt",
            "matches": derive_matches(video, candidate_title),
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": True,
            "hearing_impaired": entry["hearing_impaired"],
            "page_link": entry["page_url"],
            "display": {
                "source": "my-subs",
                "title": entry["media_title"],
                "release": entry["release_info"],
                "detail_url": entry["page_url"],
                "downloads": entry["downloads"],
            },
            "provider_payload": provider_payload,
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        download_url = payload.get("download_url")
        if not download_url:
            raise ValueError("my_subs download requires download_url")
        page_url = payload.get("page_url")
        body = self._http_get(download_url, referer=page_url)
        if _looks_like_html(body):
            final_url = extract_download_url(body, download_url)
            if not final_url:
                raise ValueError("my_subs download gate did not expose REAL_URL")
            body = self._http_get(final_url, referer=download_url)
        return _content_payload(body)


def _content_payload(body):
    if not body:
        return {
            "content_b64": "",
            "content_sha256": "",
            "content_type": "application/x-subrip",
            "format": "srt",
            "encoding": "utf-8",
            "empty": True,
        }
    try:
        body.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "latin-1"
    return {
        "content_b64": _base64.b64encode(body).decode("ascii"),
        "content_sha256": _hashlib.sha256(body).hexdigest(),
        "content_type": "application/x-subrip",
        "format": "srt",
        "encoding": encoding,
        "empty": False,
    }
