"""Sous-Titres.eu provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import io
import os
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar

PROVIDER_ID = "soustitreseu"
BASE_URL = "https://www.sous-titres.eu"
SEARCH_URL = f"{BASE_URL}/search.html"
HTTP_TIMEOUT_SECONDS = 15
# Transport-level retry for transient network failures (connection reset, DNS
# blip, read timeout, 5xx, 429). Mirrors upstream subliminal's RetryingSession:
# a single transient blip should not abort a search/download.
HTTP_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8.0
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SUPPORTED_LANGUAGES = {"eng": "en", "fra": "fr"}
ALPHA2_TO_ALPHA3 = {value: key for key, value in SUPPORTED_LANGUAGES.items()}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
LANGUAGE_ORDER = ("eng", "fra")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

_MEDIA_ROW_RE = re.compile(
    r"<li\b[^>]*class=['\"](?P<class>[^'\"]*\b(?:serie|film)\b[^'\"]*)['\"][^>]*>(?P<body>.*?)</li>",
    re.I | re.S,
)
_ANCHOR_RE = re.compile(r"<a\b[^>]*href=['\"](?P<href>[^'\"]+)['\"][^>]*>(?P<body>.*?)</a>", re.I | re.S)
_H3_RE = re.compile(r"<h3\b[^>]*>(?P<body>.*?)</h3>", re.I | re.S)
_SPAN_RE = re.compile(
    r"<span\b[^>]*class=['\"](?P<class>[^'\"]+)['\"][^>]*>(?P<body>.*?)</span>",
    re.I | re.S,
)
_ANY_SPAN_RE = re.compile(r"<span\b[^>]*>(?P<body>.*?)</span>", re.I | re.S)
_ARCHIVE_RE = re.compile(
    r"<a\b(?=[^>]*href=['\"](?P<href>[^'\"]+)['\"])(?=[^>]*class=['\"][^'\"]*\bsubList\b[^'\"]*['\"])[^>]*>(?P<body>.*?)</a>",
    re.I | re.S,
)
_IMG_LANG_RE = re.compile(r"<img\b[^>]*(?:alt|title)=['\"](?P<lang>[a-z]{2})['\"][^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_YEAR_RE = re.compile(r"\((?P<year>\d{4})\)\s*$")
_EPISODE_LABEL_RE = re.compile(r"(?P<season>\d{1,2})\s*(?:x|×)\s*(?P<episode>\d{1,3})", re.I)
_SEASON_LABEL_RE = re.compile(r"\bS(?P<season>\d{1,2})\b", re.I)
# Language tags in subtitle and archive names. Soustitres.eu writes English as VO or EN
# and French as VF or FR, and a bilingual archive as ENFR. VO, VF, ENFR and the
# three-letter codes are never ordinary words, so they count in any case. The bare
# two-letter en/fr collide with French words ("Asterix.en.Bretagne"), so they count only
# in capitals, or in any case as the last token before the extension.
_LANGUAGE_TAGS = {
    "vo": ("eng",),
    "eng": ("eng",),
    "vf": ("fra",),
    "fre": ("fra",),
    "enfr": ("eng", "fra"),
}
_TWO_LETTER_TAGS = {"en": "eng", "fr": "fra"}
_NAME_EXTENSIONS = frozenset(extension[1:] for extension in SUBTITLE_EXTENSIONS) | {"zip", "rar", "7z"}
_NAME_TOKEN_SPLIT_RE = re.compile(r"[^0-9A-Za-z]+")


def parse_search_results(body):
    text = _decode_html(body)
    rows = []
    for match in _MEDIA_ROW_RE.finditer(text):
        class_name = match.group("class")
        media_type = "series" if re.search(r"\bserie\b", class_name, re.I) else "film"
        h3 = _H3_RE.search(match.group("body"))
        if not h3:
            continue
        anchor = _ANCHOR_RE.search(h3.group("body"))
        if not anchor:
            continue
        title, year, aliases = _title_from_heading(anchor.group("body"))
        if not title:
            continue
        rows.append(
            {
                "media_type": media_type,
                "title": title,
                "year": year,
                "aliases": aliases,
                "exact": bool(re.search(r"\bexact\b", class_name, re.I)),
                "url": _absolute_url(anchor.group("href")),
            }
        )
    return rows


def parse_archive_rows(body, page_url, media_type):
    text = _decode_html(body)
    rows = []
    for match in _ARCHIVE_RE.finditer(text):
        block = match.group("body")
        fields = _span_fields(block)
        filename = (
            fields.get("filenameSerie")
            or fields.get("filenameFilm")
            or fields.get("smallFilenameSerie")
            or fields.get("smallFilenameFilm")
            or _filename_from_url(match.group("href"))
        )
        if not filename:
            continue
        label = fields.get("episodenum") or ""
        season, episode = _season_episode_from_label(label)
        release_bits = [filename]
        if fields.get("team"):
            release_bits.append(fields["team"])
        if label:
            release_bits.append(label)
        rows.append(
            {
                "media_type": media_type,
                "url": urllib.parse.urljoin(page_url, html.unescape(match.group("href"))),
                "filename": filename,
                "episode_label": label,
                "season": season,
                "episode": episode,
                "languages": _languages_from_archive(filename, block),
                "release_info": " ".join(part for part in release_bits if part).strip(),
                "updated": fields.get("update") or "",
            }
        )
    return rows


def derive_matches(video, item):
    video = video or {}
    matches = []
    if item.get("media_type") == "film":
        if _title_matches(video.get("title"), item.get("title")):
            matches.append("title")
        if video.get("year") and item.get("year") and int(video.get("year")) == int(item.get("year")):
            matches.append("year")
    else:
        if _title_matches(video.get("series"), item.get("title")):
            matches.append("series")
        try:
            if int(video.get("season")) == int(item.get("season")):
                matches.append("season")
            if item.get("archive_episode") is not None and int(video.get("episode")) == int(item.get("archive_episode")):
                matches.append("episode")
        except (TypeError, ValueError):
            pass
    release_text = _normalize_release(item.get("release_info"))
    for match_name, video_key in (
        ("release_group", "release_group"),
        ("source", "source"),
        ("resolution", "resolution"),
    ):
        value = _normalize_release(video.get(video_key))
        if value and value in release_text:
            matches.append(match_name)
    return matches


class SoustitreseuProvider:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, headers=headers)
        return self._open_with_retry(request, timeout)

    def _open_with_retry(self, request, timeout):
        # Retry only raw transport failures around the urllib call. Non-transient
        # errors (4xx other than 429, parse errors, anything non-network) propagate
        # unchanged on first occurrence. All callers issue idempotent GETs.
        for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code not in RETRY_STATUS_CODES or attempt >= HTTP_MAX_ATTEMPTS:
                    raise
                _retry_sleep(attempt, error.headers.get("Retry-After") if error.code == 429 else None)
            except (urllib.error.URLError, socket.timeout, TimeoutError):
                # urllib.error.HTTPError is a URLError subclass handled above; a bare
                # URLError here is a connection-level failure (refused/DNS/reset).
                if attempt >= HTTP_MAX_ATTEMPTS:
                    raise
                _retry_sleep(attempt, None)

    def search(self, video, languages, config):
        video = dict(video or {})
        requested = _requested_languages(languages)
        if not requested:
            return []
        kind = video.get("kind")
        if kind == "episode":
            if not video.get("series") or video.get("season") is None or video.get("episode") is None:
                return []
            return self._search_episode(video, requested, dict(config or {}))
        if kind == "movie":
            if not video.get("title"):
                return []
            return self._search_movie(video, requested, dict(config or {}))
        return []

    def _search_episode(self, video, requested, config):
        title = str(video.get("series") or "").strip()
        _sleep(config)
        search_body = self._http_get(_search_url(title), referer=BASE_URL + "/")
        rows = _rank_search_rows(parse_search_results(search_body), title, "series")
        results = []
        seen = set()
        for row in rows[:3]:
            _sleep(config)
            detail_body = self._http_get(row["url"], referer=_search_url(title))
            for archive in parse_archive_rows(detail_body, row["url"], "series"):
                if not _archive_matches_episode(archive, video):
                    continue
                results.extend(self._results_for_archive(video, row, archive, requested, seen))
            if results:
                return sorted(results, key=lambda item: item["score"], reverse=True)
        return []

    def _search_movie(self, video, requested, config):
        title = str(video.get("title") or "").strip()
        _sleep(config)
        search_body = self._http_get(_search_url(title), referer=BASE_URL + "/")
        rows = _rank_search_rows(parse_search_results(search_body), title, "film", video.get("year"))
        results = []
        seen = set()
        for row in rows[:3]:
            _sleep(config)
            detail_body = self._http_get(row["url"], referer=_search_url(title))
            for archive in parse_archive_rows(detail_body, row["url"], "film"):
                results.extend(self._results_for_archive(video, row, archive, requested, seen))
            if results:
                return sorted(results, key=lambda item: item["score"], reverse=True)
        return []

    def _results_for_archive(self, video, page_row, archive, requested, seen):
        results = []
        for alpha3 in archive.get("languages") or []:
            if alpha3 not in requested:
                continue
            item = {
                **archive,
                "title": page_row["title"],
                "year": page_row.get("year"),
                "language": alpha3,
                "season": archive.get("season") if archive.get("season") is not None else video.get("season"),
                "episode": video.get("episode") if page_row["media_type"] == "series" else None,
                "archive_episode": archive.get("episode"),
            }
            key = (item["url"], alpha3)
            if key in seen:
                continue
            seen.add(key)
            results.append(self._result(video, item))
        return results

    def _result(self, video, item):
        alpha3 = item["language"]
        alpha2 = SUPPORTED_LANGUAGES[alpha3]
        matches = derive_matches(video, item)
        score = 35
        for match_name, value in (
            ("title", 25),
            ("series", 25),
            ("year", 10),
            ("season", 15),
            ("episode", 15),
            ("release_group", 6),
            ("source", 5),
            ("resolution", 4),
        ):
            if match_name in matches:
                score += value
        filename = item.get("filename") or f"soustitreseu.{_slug(item.get('title'))}.{alpha2}.zip"
        payload = {
            "provider": PROVIDER_ID,
            "schema": 1,
            "media_type": item.get("media_type"),
            "url": item["url"],
            "filename": filename,
            "title": item.get("title"),
            "year": item.get("year"),
            "season": item.get("season"),
            "episode": item.get("episode"),
            "archive_episode": item.get("archive_episode"),
            "language": alpha3,
            "release_info": item.get("release_info") or filename,
        }
        return {
            "provider": PROVIDER_ID,
            "id": f"soustitreseu-{hashlib.sha1((item['url'] + alpha3).encode('utf-8')).hexdigest()[:16]}",
            "language": {
                "alpha3": alpha3,
                "alpha2": alpha2,
                "hi": False,
                "forced": False,
            },
            "release_info": item.get("release_info") or filename,
            "filename": filename,
            "matches": matches,
            "score": min(score, 100),
            "score_without_hash": min(score, 100),
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": item["url"],
            "display": {
                "source": "sous-titres.eu",
                "title": item.get("title"),
                "release": item.get("release_info") or filename,
            },
            "provider_payload": payload,
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        url = payload.get("url")
        if not url:
            raise ValueError("soustitreseu download requires url")
        body = self._http_get(url, timeout=30)
        return _download_payload(body, payload)

    def select_archive_member(self, provider_payload, language, members, config):
        # Host lists the archive members (zip/rar); we language-pin one with the same
        # tagging _languages_from_archive uses. Returns {member, decision: pin|defer|reject}.
        del config
        payload = dict(provider_payload or {})
        payload["language"] = provider_payload.get("language") or _alpha3_for_language(language)
        member, decision = _pick_archive_member(members, payload)
        return {"member": member, "decision": decision}


def _download_payload(body, payload):
    payload = payload or {}
    # Reject broken responses up front: the download endpoint can answer with an empty
    # stream or an HTML/error page that would otherwise look like a successful download.
    if not body or not body.strip():
        raise ValueError(f"soustitreseu empty download for {payload.get('url')}")
    if _is_html_body(body):
        raise ValueError(f"soustitreseu returned an HTML/error page for {payload.get('url')}")
    if _is_archive_body(body):
        # Host-side extraction with worker member selection. A Soustitres.eu archive can
        # bundle several languages (French + English) for one release; the host lists the
        # members (zip/rar alike) and calls select_archive_member so we language-pin one
        # with our own tagging. Works for rar too, which the worker cannot list itself.
        return {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
            "select_member": True,
        }
    # Direct, non-archive subtitle body.
    return _content_payload(body, _format_from_filename(payload.get("filename")))


def _is_archive_body(body):
    return _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _pick_archive_member(members, payload):
    # Language-pin one member from host-listed archive names (tri-state pin/defer/reject).
    # No archive lib needed: the host lists zip/rar and hands us the names. Same tagging
    # _languages_from_archive uses, so selection agrees with the row's declared language.
    payload = payload or {}
    language = payload.get("language")
    subs = [
        name
        for name in (members or [])
        if not name.endswith("/")
        and _subtitle_extension(name)
        and not os.path.basename(name).startswith(".")
    ]
    tagged = {name: _language_from_subtitle_filename(name) for name in subs}
    present = {lang for lang in tagged.values() if lang}
    # Untagged archive: nothing to go on, so the host's episode pick decides.
    if not language or not present:
        return None, "defer"
    # Members are tagged, but none with the requested language (a French-only archive
    # asked for English, say). Deferring would let the host hand over another language,
    # so reject and let Bazarr fall back.
    if language not in present:
        return None, "reject"
    pool = [name for name in subs if tagged[name] == language]
    # Every member carries the requested language: the host's episode pick is safe. With
    # other or untagged members beside them, pin from the tagged ones below instead.
    if len(pool) == len(subs):
        return None, "defer"
    # A season pack carries several episodes per language; resolve the episode here too
    # before pinning, since the host cannot combine episode and language.
    season = _safe_int(payload.get("season"))
    episode = _safe_int(payload.get("episode"))
    if season is not None and episode is not None:
        episode_pool = [
            name
            for name in pool
            if _file_matches_episode(_normalize_release(os.path.basename(name)), season, episode)
        ]
        if episode_pool:
            return episode_pool[0], "pin"
        # Episode markers present but none matches: can't pin safely when other or untagged
        # languages sit beside the pool (episode-only defer would risk them), so reject.
        if any(
            _file_has_episode_marker(_normalize_release(os.path.basename(name)))
            for name in pool
        ):
            return None, "reject"
    return (pool[0], "pin") if len(pool) == 1 else (None, "reject")


def _language_from_subtitle_filename(name):
    # One subtitle file holds one language, so a name tagged with both cannot be pinned.
    languages = _name_languages(name)
    return next(iter(languages)) if len(languages) == 1 else None


def _name_languages(name):
    # The languages a subtitle or archive name is tagged with (see _LANGUAGE_TAGS). The
    # raw name is read with its case intact, since before the last token only capitals
    # make a bare EN or FR a tag. VO/VF-style tags outrank EN/FR, so a capitalised title
    # word such as the EN in "ASTERIX.EN.BRETAGNE.VF" cannot add a language.
    decomposed = unicodedata.normalize("NFKD", str(name or ""))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    tokens = [token for token in _NAME_TOKEN_SPLIT_RE.split(folded) if token]
    if tokens and tokens[-1].lower() in _NAME_EXTENSIONS:
        tokens = tokens[:-1]
    languages = set()
    for token in tokens:
        languages.update(_LANGUAGE_TAGS.get(token.lower(), ()))
    if languages:
        return languages
    languages.update(_TWO_LETTER_TAGS[token.lower()] for token in tokens if token in ("EN", "FR"))
    if tokens and tokens[-1].lower() in _TWO_LETTER_TAGS:
        languages.add(_TWO_LETTER_TAGS[tokens[-1].lower()])
    return languages


def _file_matches_episode(normalized_name, season, episode):
    # normalized_name is dot-separated (see _normalize_release), so compare the bare
    # "{season}{episode:02d}" form (Soustitres.eu writes S01E01 as "101") against whole
    # tokens. A substring/regex match would read the "720" in "720p" as S07E20.
    compact = normalized_name.lower()
    # SxxExx, tolerating the separator _normalize_release leaves between season and
    # episode (S01.E02 / S01 E02 normalize to "s01.e02"), as well as contiguous S01E02.
    if re.search(rf"(?<![a-z0-9])s0*{season}[\s._-]*e0*{episode}(?!\d)", compact):
        return True
    # NxNN with boundaries so episode 2 ("1x2") never matches "1x20" (episode 20).
    if re.search(rf"(?<![a-z0-9]){season}x0*{episode}(?!\d)", compact):
        return True
    return f"{season}{episode:02d}" in compact.split(".")


def _file_has_episode_marker(normalized_name):
    compact = normalized_name.lower()
    return bool(
        re.search(r"s\d{1,2}[\s._-]*e\d{1,3}", compact)
        or re.search(r"(?<!\d)\d{1,2}x\d{1,3}", compact)
        or any(token.isdigit() and len(token) == 3 for token in compact.split("."))
    )


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_html_body(body):
    if not body:
        return False
    head = body[:1024].lstrip().lower()
    return (
        head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or head.startswith(b"<?xml")
        or head.startswith(b"<!--")
        or b"<body" in head
        or b"<head" in head
    )


def _rank_search_rows(rows, title, media_type, year=None):
    filtered = [
        row
        for row in rows
        if row.get("media_type") == media_type
        and _row_matches_title(row, title)
        and not _row_year_conflicts(row, year)
    ]

    def score(row):
        value = 0
        if row.get("exact"):
            value += 50
        if _normalize(row.get("title")) == _normalize(title):
            value += 40
        elif _title_matches(title, row.get("title")):
            value += 20
        if year and row.get("year") and int(year) == int(row["year"]):
            value += 20
        return value

    return sorted(filtered, key=score, reverse=True)


def _row_matches_title(row, title):
    if _title_matches(title, row.get("title")):
        return True
    return any(_title_matches(title, alias) for alias in row.get("aliases") or [])


def _row_year_conflicts(row, year):
    if not year or not row.get("year"):
        return False
    try:
        return int(year) != int(row["year"])
    except (TypeError, ValueError):
        return False


def _archive_matches_episode(archive, video):
    try:
        wanted_season = int(video.get("season"))
        wanted_episode = int(video.get("episode"))
    except (TypeError, ValueError):
        return False
    if archive.get("season") != wanted_season:
        return False
    archive_episode = archive.get("episode")
    return archive_episode is None or archive_episode == wanted_episode


def _span_fields(block):
    fields = {}
    for match in _SPAN_RE.finditer(block or ""):
        class_name = (match.group("class") or "").split()[0]
        fields[class_name] = _strip_tags(match.group("body"))
    return fields


def _title_from_heading(value):
    aliases = [_strip_tags(match.group("body")).lstrip("- ").strip() for match in _ANY_SPAN_RE.finditer(value or "")]
    primary_html = _ANY_SPAN_RE.sub("", value or "")
    primary = _strip_tags(primary_html)
    year = None
    year_match = _YEAR_RE.search(primary)
    if year_match:
        year = int(year_match.group("year"))
        primary = _YEAR_RE.sub("", primary).strip()
    return primary, year, [alias for alias in aliases if alias]


def _season_episode_from_label(label):
    label = html.unescape(label or "")
    match = _EPISODE_LABEL_RE.search(label)
    if match:
        return int(match.group("season")), int(match.group("episode"))
    match = _SEASON_LABEL_RE.search(label)
    if match:
        return int(match.group("season")), None
    return None, None


def _languages_from_archive(filename, block):
    # The same name tagging as member selection, so the row's declared languages and the
    # member choice at download read a name the same way.
    languages = set(_name_languages(filename))
    for match in _IMG_LANG_RE.finditer(block or ""):
        language = ALPHA2_TO_ALPHA3.get((match.group("lang") or "").lower())
        if language:
            languages.add(language)
    return [language for language in LANGUAGE_ORDER if language in languages]


def _requested_languages(languages):
    requested = set()
    for language in languages or []:
        alpha3 = _alpha3_for_language(language)
        if alpha3 in SUPPORTED_LANGUAGES:
            requested.add(alpha3)
    return requested


def _alpha3_for_language(language):
    if isinstance(language, dict):
        alpha3 = (language.get("alpha3") or "").lower()
        if alpha3:
            return alpha3
        return ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())
    value = str(language or "").lower()
    return ALPHA2_TO_ALPHA3.get(value, value)


def _search_url(title):
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'q': title})}"


def _absolute_url(value):
    return urllib.parse.urljoin(BASE_URL + "/", html.unescape(value or ""))


def _filename_from_url(url):
    return os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url or "").path))


def _is_rar_archive(body):
    return bool(body) and (
        body.startswith(b"Rar!\x1a\x07\x00")
        or body.startswith(b"Rar!\x1a\x07\x01\x00")
    )


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _format_from_filename(filename):
    return _subtitle_extension(filename or "") or "srt"


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially a legacy codepage that never fails to decode) only reintroduces
    # mojibake. Leave encoding unset and let the host normalize.
    return {
        "content_b64": base64.b64encode(content).decode("ascii"),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_type": _content_type(subtitle_format),
        "format": subtitle_format,
        "empty": False,
    }


def _content_type(subtitle_format):
    if subtitle_format in {"ass", "ssa"}:
        return "text/x-ssa"
    if subtitle_format == "vtt":
        return "text/vtt"
    if subtitle_format == "sub":
        return "text/plain"
    return "application/x-subrip"


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(int(delay_ms), 5000) / 1000.0)


def _retry_sleep(attempt, retry_after):
    # Module-level time.sleep so tests can monkeypatch provider.time.sleep.
    delay = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    parsed = _parse_retry_after(retry_after)
    if parsed is not None:
        delay = max(delay, parsed)
    time.sleep(min(delay, RETRY_BACKOFF_CAP_SECONDS))


def _parse_retry_after(value):
    if not value:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def _title_matches(wanted, candidate):
    wanted_tokens = _tokens(wanted)
    candidate_tokens = set(_tokens(candidate))
    return bool(wanted_tokens) and all(token in candidate_tokens for token in wanted_tokens)


def _strip_tags(value):
    stripped = _TAG_RE.sub("", value or "")
    return _WS_RE.sub(" ", html.unescape(stripped)).strip()


def _decode_html(body):
    if isinstance(body, str):
        return body
    raw = body or b""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _slug(value):
    return "-".join(_tokens(value)) or "release"


def _tokens(value):
    return [token for token in _normalize(value).split(" ") if token]


def _normalize(value):
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _normalize_release(value):
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", ".", folded.lower()).strip(".")
