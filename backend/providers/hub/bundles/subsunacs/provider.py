"""SubsUnacs provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import io
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar

PROVIDER_ID = "subsunacs"
BASE_URL = "https://subsunacs.net"
SEARCH_URL = f"{BASE_URL}/search.php"
HOME_URL = f"{BASE_URL}/index.php"
HTTP_TIMEOUT_SECONDS = 10
SUPPORTED_LANGUAGES = {"bul": "bg", "eng": "en"}
ALPHA2_TO_ALPHA3 = {"bg": "bul", "en": "eng"}
SUBTITLE_EXTENSIONS = (".srt", ".sub", ".txt")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
TV_NAME_FIXES = {
    "Marvel's Daredevil": "Daredevil",
    "Marvel's Luke Cage": "Luke Cage",
    "Marvel's Iron Fist": "Iron Fist",
    "DC's Legends of Tomorrow": "Legends of Tomorrow",
    "Doctor Who (2005)": "Doctor Who",
    "Star Trek: Deep Space Nine": "Star Trek DS9",
    "Star Trek: The Next Generation": "Star Trek TNG",
    "Superman & Lois": "Superman and Lois",
}
MOVIE_NAME_FIXES = {
    "Back to the Future Part III": "Back to the Future 3",
    "Back to the Future Part II": "Back to the Future 2",
    "Bill & Ted Face the Music": "Bill Ted Face the Music",
}

_ROW_RE = re.compile(r"<tr\b[^>]*\bonmouseover=['\"][^>]*>(?P<body>.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td\b(?P<attrs>[^>]*)>(?P<body>.*?)</td>", re.I | re.S)
_ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S)
_HREF_RE = re.compile(r"\bhref=['\"](?P<href>[^'\"]+)['\"]", re.I)
_TITLE_ATTR_RE = re.compile(r"\btitle=['\"](?P<title>[^'\"]*)['\"]", re.I | re.S)
_YEAR_RE = re.compile(r"<span\b[^>]*class=['\"][^'\"]*\bsmGray\b[^'\"]*['\"][^>]*>\s*&nbsp;\((?P<year>\d{4})\)", re.I)
_RATING_RE = re.compile(r"<img\b[^>]*(?:alt|title)=['\"](?P<rating>[\d.]+)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_TITLE_EPISODE_RE = re.compile(r"^(?P<title>.+?)\s*(?:-|:)?\s+(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?:\b|$)", re.I)


def parse_search_results(body):
    text = _decode_html(body)
    rows = []
    for match in _ROW_RE.finditer(text):
        row = match.group("body")
        cells = [cell.group("body") for cell in _CELL_RE.finditer(row)]
        if len(cells) < 6:
            continue
        title_cell = next((cell for cell in cells if "tdMovie" in cell or "tooltip" in cell), cells[0])
        anchor = _first_anchor(title_cell)
        if not anchor:
            continue
        href = anchor["href"]
        if "/subtitles/" not in href:
            continue
        year_match = _YEAR_RE.search(title_cell)
        rating_match = _RATING_RE.search(cells[3] if len(cells) > 3 else "")
        title, season, episode = _title_and_episode_from_text(anchor["body"])
        rows.append(
            {
                "subtitle_id": _subtitle_id_from_href(href),
                "page_url": _absolute_url(href),
                "download_url": _download_url(href),
                "title": title,
                "season": season,
                "episode": episode,
                "year": int(year_match.group("year")) if year_match else None,
                "num_cds": _parse_int(cells[1] if len(cells) > 1 else ""),
                "fps": _parse_float(cells[2] if len(cells) > 2 else ""),
                "rating": _parse_float(rating_match.group("rating") if rating_match else ""),
                "uploader": _strip_tags(cells[5] if len(cells) > 5 else "") or None,
                "notes": _notes_from_anchor(anchor["attrs"]),
            }
        )
    return rows


def parse_detail_entries(body):
    text = _decode_html(body)
    entries = []
    for anchor in _ANCHOR_RE.finditer(text):
        attrs = anchor.group("attrs")
        href_match = _HREF_RE.search(attrs)
        if not href_match:
            continue
        href = html.unescape(href_match.group("href"))
        if "getentry.php" not in href:
            continue
        filename = _strip_tags(anchor.group("body"))
        if not _is_subtitle_file(filename):
            continue
        entries.append({"filename": os.path.basename(filename), "entry_url": _absolute_url(href)})
    return entries


def derive_matches(video, item):
    video = video or {}
    matches = []
    if item.get("media_type") == "episode":
        if _title_matches(video.get("series"), item.get("title")):
            matches.append("series")
        season, episode = _season_episode_from_filename(item.get("filename"))
        if season is not None and video.get("season") is not None and season == int(video.get("season")):
            matches.append("season")
        if episode is not None and video.get("episode") is not None and episode == int(video.get("episode")):
            matches.append("episode")
    else:
        if _title_matches(video.get("title"), item.get("title")):
            matches.append("title")
        if video.get("year") and item.get("year") and int(video.get("year")) == int(item.get("year")):
            matches.append("year")
    if item.get("fps") and video.get("fps"):
        try:
            if abs(float(item["fps"]) - float(video["fps"])) < 0.001:
                matches.append("fps")
        except (TypeError, ValueError):
            pass
    release_text = _normalize_release(f"{item.get('filename') or ''} {item.get('notes') or ''}")
    for match_name, key in (("release_group", "release_group"), ("source", "source"), ("resolution", "resolution")):
        value = _normalize_release(video.get(key))
        if value and value in release_text:
            matches.append(match_name)
    return matches


class SubsUnacsProvider:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        request = urllib.request.Request(url, headers=_headers(referer))
        with self._opener.open(request, timeout=timeout) as response:
            return response.read()

    def _http_post(self, url, data, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers = _headers(referer)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        with self._opener.open(request, timeout=timeout) as response:
            return response.read()

    def search(self, video, languages, config):
        video = dict(video or {})
        requested = _requested_languages(languages)
        if not requested:
            return []
        if video.get("kind") == "episode":
            if not video.get("series") or video.get("season") is None or video.get("episode") is None:
                return []
            media_type = "episode"
            search_series = _search_title(video.get("series"), TV_NAME_FIXES)
            title = _episode_query_title(search_series, video)
            match_video = {**video, "series": search_series}
        elif video.get("kind") == "movie":
            if not video.get("title"):
                return []
            media_type = "movie"
            title = _search_title(video["title"], MOVIE_NAME_FIXES)
            match_video = {**video, "title": title}
        else:
            return []

        results = []
        seen = set()
        config = dict(config or {})
        for alpha3, variants in requested.items():
            _sleep(config)
            rows = parse_search_results(self._http_post(SEARCH_URL, _search_payload(video, title, alpha3), referer=HOME_URL))
            for row in rows[:20]:
                if not _row_matches_video(row, match_video, media_type):
                    continue
                _sleep(config)
                try:
                    entries = _entries_from_download_body(self._http_get(row["download_url"], referer=SEARCH_URL), row["download_url"], row)
                except Exception:
                    continue
                for entry in entries:
                    if not _file_matches_video(entry["filename"], video, media_type):
                        continue
                    for variant in variants:
                        if not _variant_matches_entry(variant, entry["filename"]):
                            continue
                        item = {**row, **entry, "media_type": media_type, "language": variant}
                        key = (row["download_url"], _entry_identity(entry), _language_variant_key(variant))
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(self._result(match_video, item))
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _result(self, video, item):
        language = item["language"]
        language_key = ":".join(str(value) for value in _language_variant_key(language))
        matches = derive_matches(video, item)
        score = 35
        for match_name, value in (
            ("title", 20),
            ("series", 20),
            ("year", 10),
            ("season", 12),
            ("episode", 15),
            ("release_group", 7),
            ("source", 5),
            ("resolution", 4),
            ("fps", 4),
        ):
            if match_name in matches:
                score += value
        payload = {
            "provider": PROVIDER_ID,
            "schema": 1,
            "download_url": item["download_url"],
            "entry_url": item.get("entry_url"),
            "filename": item["filename"],
            "path": item.get("path"),
            "title": item.get("title"),
            "year": item.get("year"),
            "season": item.get("season"),
            "episode": item.get("episode"),
            "language": language["alpha3"],
            "release_info": item["filename"],
        }
        identity = item.get("path") or item.get("entry_url") or item["filename"]
        return {
            "provider": PROVIDER_ID,
            "id": f"subsunacs-{hashlib.sha1((item['download_url'] + identity + language_key).encode('utf-8')).hexdigest()[:16]}",
            "language": {
                "alpha3": language["alpha3"],
                "alpha2": SUPPORTED_LANGUAGES[language["alpha3"]],
                "hi": language["hi"],
                "forced": language["forced"],
            },
            "release_info": item["filename"],
            "filename": item["filename"],
            "matches": matches,
            "score": min(score, 100),
            "score_without_hash": min(score, 100),
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": language["hi"],
            "page_link": item.get("page_url") or item["download_url"],
            "display": {
                "source": "subsunacs.net",
                "title": item.get("title"),
                "release": item["filename"],
                "uploader": item.get("uploader"),
            },
            "provider_payload": payload,
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        if payload.get("entry_url"):
            body = self._http_get(payload["entry_url"], referer=payload.get("download_url") or SEARCH_URL)
            return self._resolve_download(body, payload, referer=payload.get("download_url") or SEARCH_URL)
        url = payload.get("download_url")
        if not url:
            raise ValueError("subsunacs download requires download_url or entry_url")
        body = self._http_get(url, referer=SEARCH_URL)
        return self._resolve_download(body, payload, referer=url)

    def _resolve_download(self, body, payload, referer):
        # Reject broken responses up front: the download endpoint can answer with an empty
        # stream or an HTML/error page that would otherwise look like a successful download.
        if not body or not body.strip():
            raise ValueError(f"subsunacs empty download for {payload.get('download_url')}")
        if _is_html_body(body):
            # An HTML detail page lists getentry.php members; resolve the wanted member and
            # fetch its direct subtitle bytes.
            entries = parse_detail_entries(body)
            if entries:
                selected = select_subtitle_file(entries, payload)
                data = self._http_get(selected["entry_url"], referer=referer)
                return _download_payload(data, {**payload, "filename": selected["filename"]})
            raise ValueError(f"subsunacs returned an HTML/error page for {payload.get('download_url')}")
        return _download_payload(body, payload)


def select_subtitle_file(files, payload):
    if not files:
        raise ValueError("subsunacs download contains no supported subtitle files")
    wanted_path = payload.get("path")
    if wanted_path:
        for item in files:
            if item.get("path") == wanted_path:
                return item
    wanted = payload.get("filename")
    for item in files:
        if item["filename"] == wanted:
            return item
    release_info = _normalize_release(payload.get("release_info") or wanted)

    def score(index_item):
        index, item = index_item
        value = max(0, 10 - index)
        name = _normalize_release(item["filename"])
        if release_info:
            for token in [part for part in release_info.split(".") if len(part) > 2]:
                if token in name:
                    value += 4
        if item["filename"].lower().endswith(".srt"):
            value += 5
        return value

    return max(enumerate(files), key=score)[1]


def _entries_from_download_body(body, download_url, row=None):
    entries = parse_detail_entries(body)
    if entries:
        return entries
    if _is_archive_body(body):
        # Host-side archive (zip/rar/7z): do not list members in the worker. Produce a
        # single candidate whose download() hands the raw bytes back to the host.
        return [{"filename": _archive_release_name(row, download_url), "archive": True}]
    return []


def _archive_release_name(row, download_url):
    title = (row or {}).get("title")
    if title:
        season = (row or {}).get("season")
        episode = (row or {}).get("episode")
        if season is not None and episode is not None:
            return f"{title} S{int(season):02d}E{int(episode):02d}"
        return str(title)
    return os.path.basename(urllib.parse.urlparse(download_url or "").path.rstrip("/")) or "subsunacs.archive"


def _entry_identity(entry):
    return entry.get("path") or entry.get("entry_url") or entry.get("filename")


def _is_rar_archive(body):
    return bool(body) and (body.startswith(b"Rar!\x1a\x07\x00") or body.startswith(b"Rar!\x1a\x07\x01\x00"))


def _is_7z_archive(body):
    return bool(body) and body.startswith(b"7z\xbc\xaf\x27\x1c")


def _is_archive_body(body):
    # zip, rar, and 7z are all extracted host-side (Provider Hub v1.1+). download() hands
    # the raw bytes back as archive_b64 for the host to list, select, and decode.
    return _is_rar_archive(body) or _is_7z_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _is_ignored_txt_file(filename):
    lowered = os.path.basename(filename or "").lower()
    return lowered.endswith(".txt") and bool(
        re.search(r"subsunacs\.net|read ?me|procheti", lowered, re.I)
    )


def _is_subtitle_file(filename):
    lowered = (filename or "").lower()
    return lowered.endswith(SUBTITLE_EXTENSIONS) and not _is_ignored_txt_file(filename)


def _first_anchor(value):
    match = _ANCHOR_RE.search(value or "")
    if not match:
        return None
    href_match = _HREF_RE.search(match.group("attrs"))
    if not href_match:
        return None
    return {
        "href": html.unescape(href_match.group("href")),
        "attrs": match.group("attrs"),
        "body": match.group("body"),
    }


def _notes_from_anchor(attrs):
    match = _TITLE_ATTR_RE.search(attrs or "")
    if not match:
        return ""
    value = html.unescape(match.group("title"))
    return _strip_tags(re.sub(r"<img\b[^>]*>", "", value, flags=re.I))


def _subtitle_id_from_href(href):
    match = re.search(r"-(\d+)/?!?$", href or "")
    return match.group(1) if match else None


def _download_url(href):
    url = _absolute_url(href)
    if not url.endswith("/"):
        url += "/"
    return url + "!"


def _absolute_url(value):
    return urllib.parse.urljoin(BASE_URL + "/", html.unescape(value or ""))


def _row_matches_video(row, video, media_type):
    if media_type == "movie":
        if not _title_matches(video.get("title"), row.get("title")):
            return False
        return not video.get("year") or row.get("year") == int(video.get("year"))
    if not _title_matches(video.get("series"), row.get("title")):
        return False
    if row.get("season") is not None and row["season"] != int(video.get("season")):
        return False
    if row.get("episode") is not None and row["episode"] != int(video.get("episode")):
        return False
    return True


def _file_matches_video(filename, video, media_type):
    if media_type == "movie":
        return True
    season, episode = _season_episode_from_filename(filename)
    if season is None or episode is None:
        return True
    return season == int(video.get("season")) and episode == int(video.get("episode"))


def _season_episode_from_filename(filename):
    normalized = _normalize_release(filename)
    match = re.search(r"s(?P<season>\d{1,2})e(?P<episode>\d{1,3})", normalized)
    if match:
        return int(match.group("season")), int(match.group("episode"))
    match = re.search(r"(?P<season>\d{1,2})x(?P<episode>\d{1,3})", normalized)
    if match:
        return int(match.group("season")), int(match.group("episode"))
    match = re.search(r"(?:^|\.)(?P<season>\d)(?P<episode>\d{2})(?:\.|$)", normalized)
    if match:
        return int(match.group("season")), int(match.group("episode"))
    return None, None


def _requested_languages(languages):
    grouped = {}
    for language in languages or []:
        alpha3 = _alpha3_for_language(language)
        if alpha3 not in SUPPORTED_LANGUAGES:
            continue
        variant = {
            "alpha3": alpha3,
            "hi": bool(language.get("hi")) if isinstance(language, dict) else False,
            "forced": bool(language.get("forced")) if isinstance(language, dict) else False,
        }
        grouped.setdefault(alpha3, []).append(variant)
    return grouped


def _language_variant_key(language):
    return (language["alpha3"], bool(language["hi"]), bool(language["forced"]))


def _entry_flags(filename):
    normalized = _normalize_release(filename)
    forced = bool(re.search(r"(?:^|\.)forced(?:\.|$)", normalized))
    hi = bool(re.search(r"(?:^|\.)(?:hi|sdh|cc)(?:\.|$)", normalized))
    return forced, hi


def _variant_matches_entry(variant, filename):
    forced, hi = _entry_flags(filename)
    if bool(variant.get("forced")) != forced:
        return False
    if bool(variant.get("hi")) != hi:
        return False
    return True


def _alpha3_for_language(language):
    if isinstance(language, dict):
        alpha3 = (language.get("alpha3") or "").lower()
        if alpha3:
            return alpha3
        return ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())
    value = str(language or "").lower()
    return ALPHA2_TO_ALPHA3.get(value, value)


def _search_payload(video, title, alpha3):
    payload = {
        "m": title,
        "l": 1 if alpha3 == "eng" else 0,
        "c": "",
        "y": "",
        "action": "   \u0422\u044a\u0440\u0441\u0438   ",
        "a": "",
        "d": "",
        "u": "",
        "g": "",
        "t": "",
        "imdbcheck": 1,
    }
    if (video or {}).get("kind") == "movie" and (video or {}).get("year"):
        payload["y"] = int(video["year"])
    return payload


def _episode_query_title(series, video):
    return f"{series} {int(video.get('season')):02d} {int(video.get('episode')):02d}"


def _title_and_episode_from_text(value):
    title = _strip_tags(value)
    match = _TITLE_EPISODE_RE.search(title)
    if not match:
        return title, None, None
    return (
        match.group("title").strip(" -:"),
        int(match.group("season")),
        int(match.group("episode")),
    )


def _search_title(title, replacements):
    value = str(title or "")
    for old, new in replacements.items():
        if value == old or value.startswith(old):
            value = value.replace(old, new, 1)
            break
    return _ascii_fold(value).replace("'", "")


def _headers(referer=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8,bg;q=0.7",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _parse_int(value):
    try:
        return int(_strip_tags(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_float(value):
    try:
        return float(_strip_tags(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normalize_line_endings(content):
    return (content or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _download_payload(body, payload):
    payload = payload or {}
    # Reject broken responses up front: the endpoint can answer with an empty stream or an
    # HTML/error page that would otherwise look like a successful download.
    if not body or not body.strip():
        raise ValueError(f"subsunacs empty download for {payload.get('download_url')}")
    if _is_html_body(body):
        raise ValueError(f"subsunacs returned an HTML/error page for {payload.get('download_url')}")
    if _is_archive_body(body):
        # Host-side extraction (Provider Hub v1.1+): hand the raw zip/rar/7z bytes back to
        # the host, which lists it, decodes the chosen member, and detects encoding.
        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        # A season-pack zip can hold several episodes; the host's episode-only pick can
        # land on the wrong member when the same number repeats across seasons. When we can
        # list the zip and a single member matches BOTH the requested season and episode,
        # pin it; otherwise (rar/7z, movies, no/ambiguous match) defer to host episode
        # selection, which fails loudly on a true no-match.
        member = _select_zip_member(body, payload)
        if member is not None:
            archive["member"] = member
        else:
            archive["episode"] = payload.get("episode")
        return archive
    # Direct, non-archive subtitle body.
    return _content_payload(_normalize_line_endings(body), _subtitle_extension(payload.get("filename")) or "srt")


def _select_zip_member(body, payload):
    # Pin the zip member matching the requested season+episode. Listing only, no extraction
    # or decoding: the host reads the named member (an exact namelist match that hard-fails
    # on mismatch) and runs chardet. Returns None for rar/7z (not stdlib-listable), a single
    # member (nothing to disambiguate), movies (no episode to narrow on), or when the match
    # is not a unique winner, so the caller falls back to host-side episode selection.
    payload = payload or {}
    if _is_rar_archive(body) or _is_7z_archive(body) or not zipfile.is_zipfile(io.BytesIO(body or b"")):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and _is_subtitle_file(name)
            and not os.path.basename(name).startswith(".")
        ]
    if len(members) < 2:
        return None  # a lone member: the host's episode pick already lands here
    season = _safe_int(payload.get("season"))
    episode = _safe_int(payload.get("episode"))
    if season is None or episode is None:
        return None  # movie or unknown episode: nothing to narrow on, defer to the host
    matches = [name for name in members if _member_has_episode(name, season, episode)]
    if len(matches) == 1:
        return matches[0]
    # Zero matches (pinning a wrong member would hard-fail the host download) or several
    # tied matches (cannot confidently disambiguate): defer to host episode selection.
    return None


def _member_has_episode(name, season, episode):
    # Match the requested SxxEyy as a delimited token, tolerating a separator between the
    # season and episode parts (S01E02, S01.E02, S01 E02, S01-E02), the NxNN form (1x02),
    # and the whole-token "{season}{episode:02d}" form (e.g. 101). The (?!\d) guard stops a
    # 3-digit code from matching a longer number; for the bare-digit form the digits must be
    # a standalone token (delimited on both sides) so "720" never matches "720p"/"x264".
    text = (name or "").lower()
    return bool(
        re.search(rf"(?<![a-z0-9])s0*{season}[\s._-]*e0*{episode}(?!\d)", text)
        or re.search(rf"(?<!\d){season}x0*{episode}(?!\d)", text)
        or re.search(rf"(?<![a-z0-9]){season}{episode:02d}(?![a-z0-9])", text)
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
    return "application/x-subrip" if subtitle_format == "srt" else "text/plain"


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(int(delay_ms), 5000) / 1000.0)


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
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "windows-1251", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _tokens(value):
    return [token for token in _normalize(value).split(" ") if token]


def _normalize(value):
    if value is None:
        return ""
    return _NON_ALNUM_RE.sub(" ", _ascii_fold(value).lower()).strip()


def _normalize_release(value):
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", ".", _ascii_fold(value).lower()).strip(".")


def _ascii_fold(value):
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
