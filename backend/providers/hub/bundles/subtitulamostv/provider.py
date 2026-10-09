"""SubtitulamosTV provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


PROVIDER_ID = "subtitulamostv"
BASE_URL = "https://www.subtitulamos.tv"
SEARCH_URL = f"{BASE_URL}/search/query"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
HTTP_TIMEOUT_SECONDS = 10
HTTP_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
CONTENT_TYPES = {
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "ass": "text/x-ssa",
    "ssa": "text/x-ssa",
}
SUBTITLE_EXTENSIONS = {"srt", "vtt", "ass", "ssa", "sub"}
LATIN_AMERICAN_SPANISH_COUNTRIES = {
    "AR",
    "BO",
    "CL",
    "CO",
    "CR",
    "DO",
    "EC",
    "GT",
    "HN",
    "MX",
    "NI",
    "PA",
    "PE",
    "PR",
    "PY",
    "SV",
    "US",
    "UY",
    "VE",
}


SITE_LANGUAGE_PAYLOADS = {
    "Español": {"alpha3": "spa", "alpha2": "es"},
    "Español (España)": {"alpha3": "spa", "alpha2": "es"},
    "Español (Latinoamérica)": {
        "alpha3": "spa",
        "alpha2": "es",
        "country_alpha2": "MX",
        "ietf": "es-MX",
    },
    "Català": {"alpha3": "cat", "alpha2": "ca"},
    "English": {"alpha3": "eng", "alpha2": "en"},
    "Galego": {"alpha3": "glg", "alpha2": "gl"},
    "Portuguese": {"alpha3": "por", "alpha2": "pt"},
    "English (US)": {
        "alpha3": "eng",
        "alpha2": "en",
        "country_alpha2": "US",
        "ietf": "en-US",
    },
    "English (UK)": {
        "alpha3": "eng",
        "alpha2": "en",
        "country_alpha2": "GB",
        "ietf": "en-GB",
    },
    "Brazilian": {
        "alpha3": "por",
        "alpha2": "pt",
        "country_alpha2": "BR",
        "ietf": "pt-BR",
    },
}


def _attrs_dict(attrs):
    return {name: value or "" for name, value in attrs}


def _class_tokens(value):
    return set((value or "").split())


def _coerce_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _clean_text(value):
    return re.sub(r"\s+", " ", html.unescape(_coerce_text(value))).strip()


def normalize_search_title(title):
    return re.sub(r"\s+\(\d{4}\)$", "", _clean_text(title)).lower()


def build_queries(video):
    video = video or {}
    if video.get("kind") != "episode":
        return []

    series = _clean_text(video.get("series"))
    if not series or video.get("season") is None or video.get("episode") is None:
        return []

    year = video.get("year")
    if year:
        return [f"{series} ({year})", series]
    return [series]


def build_search_url(query):
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'q': query})}"


def parse_search_results(body):
    try:
        payload = json.loads((body or b"").decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    results = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        show_id = _clean_text(item.get("show_id"))
        show_name = _clean_text(item.get("show_name"))
        if show_id and show_name:
            results.append({"show_id": show_id, "show_name": show_name})
    return results


def filter_exact_show_results(results, search_title):
    expected = normalize_search_title(search_title)
    return [
        result
        for result in results
        if normalize_search_title(result.get("show_name")) == expected
    ]


def _alpha3(language):
    if isinstance(language, dict):
        return language.get("alpha3")
    return getattr(language, "alpha3", None)


def _alpha2(language):
    if isinstance(language, dict):
        return language.get("alpha2")
    return getattr(language, "alpha2", None)


def _country_alpha2(language):
    if isinstance(language, dict):
        return language.get("country_alpha2") or language.get("country")
    country = getattr(language, "country", None)
    return getattr(country, "alpha2", None)


def _language_key(language):
    alpha3 = _alpha3(language)
    country = (_country_alpha2(language) or "").upper() or None
    if alpha3 == "spa" and country in LATIN_AMERICAN_SPANISH_COUNTRIES:
        return "Español (Latinoamérica)"
    if alpha3 == "spa":
        return "Español"
    if alpha3 == "eng" and country == "US":
        return "English (US)"
    if alpha3 == "eng" and country == "GB":
        return "English (UK)"
    if alpha3 == "eng":
        return "English"
    if alpha3 == "por" and country == "BR":
        return "Brazilian"
    if alpha3 == "por":
        return "Portuguese"
    if alpha3 == "cat":
        return "Català"
    if alpha3 == "glg":
        return "Galego"
    return None


def _supported_requested_languages(languages):
    supported = []
    for language in languages or []:
        if _language_key(language):
            supported.append(dict(language) if isinstance(language, dict) else _language_payload(language))
    return supported


def _language_payload(language):
    payload = {
        "alpha3": _alpha3(language),
        "alpha2": _alpha2(language),
    }
    country = _country_alpha2(language)
    if country:
        payload["country_alpha2"] = country
    return {key: value for key, value in payload.items() if value}


def site_language_to_payload(label, requested_languages=None):
    base = SITE_LANGUAGE_PAYLOADS.get(_clean_text(label))
    if not base:
        return None
    if requested_languages:
        site_key = _clean_text(label)
        accepted_keys = {site_key}
        if site_key == "Español (España)":
            accepted_keys.add("Español")
        for requested in requested_languages:
            if _language_key(requested) in accepted_keys:
                return dict(requested)
        return None
    return dict(base)


class ChoiceParser(HTMLParser):
    def __init__(self, container_id):
        super().__init__()
        self.container_id = container_id
        self.container_depth = 0
        self.current = None
        self.choices = []

    def handle_starttag(self, tag, attrs):
        attrs = _attrs_dict(attrs)
        if self.container_depth:
            self.container_depth += 1
            if tag == "a":
                self.current = {
                    "href": attrs.get("href", ""),
                    "selected": "selected" in _class_tokens(attrs.get("class")),
                    "text": [],
                }
            return

        if attrs.get("id") == self.container_id:
            self.container_depth = 1

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if self.current is not None and tag == "a":
            text = _clean_text(" ".join(self.current["text"]))
            match = re.search(r"\d+", text)
            if match:
                self.choices.append(
                    {
                        "href": self.current["href"],
                        "selected": self.current["selected"],
                        "text": text,
                        "number": int(match.group(0)),
                    }
                )
            self.current = None

        if self.container_depth:
            self.container_depth -= 1


def parse_choice_links(body, container_id):
    parser = ChoiceParser(container_id)
    parser.feed((body or b"").decode("utf-8", errors="replace"))
    return parser.choices


class EpisodeTitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_episode_name = False
        self.in_heading = False
        self.depth = 0
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = _attrs_dict(attrs)
        if attrs.get("id") == "episode-name":
            self.in_episode_name = True
            self.depth = 1
            return
        if self.in_episode_name:
            self.depth += 1
            if tag == "h3":
                self.in_heading = True

    def handle_data(self, data):
        if self.in_heading:
            self.title_parts.append(data)

    def handle_endtag(self, tag):
        if self.in_heading and tag == "h3":
            self.in_heading = False
        if self.in_episode_name:
            self.depth -= 1
            if self.depth <= 0:
                self.in_episode_name = False


class VersionParser(HTMLParser):
    def __init__(self, requested_languages, page_url):
        super().__init__()
        self.requested_languages = requested_languages
        self.page_url = page_url
        self.depth = 0
        self.current = None
        self.capture = None
        self.language_capture = False
        self.language_parts = []
        self.current_language = ""
        self.anchor_href = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = _attrs_dict(attrs)
        classes = _class_tokens(attrs.get("class"))
        if self.depth:
            self.depth += 1
            if tag == "a" and attrs.get("href"):
                self.anchor_href = attrs["href"]
            if "language-name" in classes:
                self.capture = "language"
            elif "text" in classes and "spaced" in classes:
                self.capture = "release_info"
            elif "download-button" in classes:
                self.current["unavailable"] = self.current["unavailable"] or "unavailable" in classes
                self.current["download_url"] = self.anchor_href or attrs.get("href", "")
            return

        if "language-name" in classes:
            self.language_capture = True
            self.language_parts = []
            return

        if "version-container" in classes:
            self.depth = 1
            self.current = {
                "language": [self.current_language],
                "release_info": [],
                "download_url": "",
                "unavailable": False,
            }

    def handle_data(self, data):
        if self.current is not None and self.capture:
            self.current[self.capture].append(data)
        elif self.language_capture:
            self.language_parts.append(data)

    def handle_endtag(self, tag):
        if self.language_capture and tag in {"div", "span", "p"}:
            self.current_language = _clean_text(" ".join(self.language_parts))
            self.language_capture = False
        if self.capture and tag in {"div", "span", "p"}:
            self.capture = None
        if tag == "a":
            self.anchor_href = None
        if self.depth:
            self.depth -= 1
            if self.depth == 0 and self.current is not None:
                self._finish_current()
                self.current = None

    def _finish_current(self):
        if self.current["unavailable"]:
            return
        language_label = _clean_text(" ".join(self.current["language"]))
        language = site_language_to_payload(language_label, self.requested_languages)
        download_url = self.current.get("download_url")
        if not language or not download_url:
            return
        self.rows.append(
            {
                "language": language,
                "release_info": _clean_text(" ".join(self.current["release_info"])),
                "download_url": urllib.parse.urljoin(BASE_URL, download_url),
                "page_url": self.page_url,
            }
        )


def parse_episode_page(body, requested_languages, page_url):
    decoded = (body or b"").decode("utf-8", errors="replace")
    title_parser = EpisodeTitleParser()
    title_parser.feed(decoded)
    title = _clean_text(" ".join(title_parser.title_parts))

    version_parser = VersionParser(requested_languages, page_url)
    version_parser.feed(decoded)
    rows = version_parser.rows
    for row in rows:
        row["title"] = title.lower()
    return rows


def _pick_choice(choices, number):
    try:
        expected = int(number)
    except (TypeError, ValueError):
        return None
    return next((choice for choice in choices if choice["number"] == expected), None)


def _matches():
    return ["episode", "season", "series", "title"]


def _retry_after_seconds(error):
    try:
        value = error.headers.get("Retry-After")
    except AttributeError:
        return None
    if not value:
        return None
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, RETRY_BACKOFF_CAP_SECONDS)


def _backoff_seconds(attempt):
    delay = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    return min(delay, RETRY_BACKOFF_CAP_SECONDS)


def _http_get(url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # Retry only transient server-side / rate-limit statuses; 4xx
            # (other than 429) propagate unchanged on the first occurrence.
            if error.code not in RETRY_STATUS_CODES or attempt >= HTTP_MAX_ATTEMPTS:
                raise
            delay = _retry_after_seconds(error)
            if delay is None:
                delay = _backoff_seconds(attempt)
            time.sleep(delay)
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            # Connection refused / DNS failure / reset / read timeout.
            if attempt >= HTTP_MAX_ATTEMPTS:
                raise
            time.sleep(_backoff_seconds(attempt))


def _sleep(config):
    try:
        delay_ms = int((config or {}).get("request_delay_ms") or 0)
    except (TypeError, ValueError):
        delay_ms = 0
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)


def _format_from_url(url):
    ext = os.path.splitext(urllib.parse.urlparse(url or "").path)[1].lower().lstrip(".")
    return ext if ext in SUBTITLE_EXTENSIONS else "srt"


def _normalize_subtitle_bytes(body):
    return (body or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _content_payload(body, subtitle_format):
    body = _normalize_subtitle_bytes(body)
    try:
        body.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "latin-1"
    return {
        "content_b64": base64.b64encode(body).decode("ascii"),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "content_type": CONTENT_TYPES.get(subtitle_format, "text/plain"),
        "format": subtitle_format,
        "encoding": encoding,
        "empty": False,
    }


class SubtitulamosTVProvider:
    def __init__(self):
        self._http_get = _http_get

    def search(self, video, languages, config):
        requested_languages = _supported_requested_languages(languages)
        if not requested_languages:
            return []

        queries = build_queries(video)
        if not queries:
            return []

        config = dict(config or {})
        for query in queries:
            _sleep(config)
            search_body = self._http_get(build_search_url(query), timeout=HTTP_TIMEOUT_SECONDS, referer=BASE_URL)
            search_results = filter_exact_show_results(parse_search_results(search_body), query)
            if not search_results:
                continue

            for show in search_results:
                page_url = urllib.parse.urljoin(BASE_URL, f"/shows/{show['show_id']}")
                _sleep(config)
                page_body = self._http_get(page_url, timeout=HTTP_TIMEOUT_SECONDS, referer=BASE_URL)

                season = _pick_choice(parse_choice_links(page_body, "season-choices"), video.get("season"))
                if not season:
                    continue
                if not season["selected"] and season["href"]:
                    page_url = urllib.parse.urljoin(BASE_URL, season["href"])
                    _sleep(config)
                    page_body = self._http_get(page_url, timeout=HTTP_TIMEOUT_SECONDS, referer=BASE_URL)

                episode = _pick_choice(parse_choice_links(page_body, "episode-choices"), video.get("episode"))
                if not episode:
                    continue
                episode_url = urllib.parse.urljoin(BASE_URL, episode["href"])
                if episode["href"] and not episode["selected"]:
                    _sleep(config)
                    page_body = self._http_get(episode_url, timeout=HTTP_TIMEOUT_SECONDS, referer=page_url)
                    page_url = episode_url
                elif episode_url:
                    page_url = episode_url

                rows = parse_episode_page(page_body, requested_languages, page_url)
                candidates = [
                    self._candidate_from_row(row, video)
                    for row in rows
                ]
                if candidates:
                    return candidates
        return []

    def _candidate_from_row(self, row, video):
        download_url = row["download_url"]
        release_info = row.get("release_info") or ""
        return {
            "provider": PROVIDER_ID,
            "id": download_url,
            "language": row["language"],
            "release_info": release_info,
            "filename": f"{PROVIDER_ID}.{hashlib.md5(download_url.encode()).hexdigest()[:12]}.srt",
            "matches": _matches(),
            "score": 100,
            "score_without_hash": 100,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": row["page_url"],
            "display": {
                "source": "subtitulamos.tv",
                "series": _clean_text((video or {}).get("series")),
                "title": row.get("title") or "",
                "release": release_info,
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "download_url": download_url,
                "page_url": row["page_url"],
                "video": dict(video or {}),
            },
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        download_url = payload.get("download_url")
        if not download_url:
            raise ValueError("subtitulamostv download requires download_url")
        body = self._http_get(
            download_url,
            timeout=HTTP_TIMEOUT_SECONDS,
            referer=payload.get("page_url"),
        )
        return _content_payload(body, _format_from_url(download_url))
