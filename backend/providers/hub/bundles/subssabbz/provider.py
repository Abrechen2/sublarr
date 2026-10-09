"""SubsSabBz provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import io
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar

PROVIDER_ID = "subssabbz"
BASE_URL = "http://subs.sab.bz"
SEARCH_URL = f"{BASE_URL}/index.php?"
HTTP_TIMEOUT_SECONDS = 30
SUPPORTED_LANGUAGES = {"bul": "bg", "eng": "en"}
ALPHA2_TO_ALPHA3 = {"bg": "bul", "en": "eng"}
SUBTITLE_EXTENSIONS = (".srt", ".sub")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
TV_NAME_FIXES = {
    "Marvel's Daredevil": "Daredevil",
    "Marvel's Luke Cage": "Luke Cage",
    "Marvel's Iron Fist": "Iron Fist",
    "Marvel's Jessica Jones": "Jessica Jones",
    "DC's Legends of Tomorrow": "Legends of Tomorrow",
    "Doctor Who (2005)": "Doctor Who",
    "Star Trek: Deep Space Nine": "Star Trek DS9",
    "Star Trek: The Next Generation": "Star Trek TNG",
    "Superman & Lois": "Superman and Lois",
}
MOVIE_NAME_FIXES = {
    "Back to the Future Part": "Back to the Future",
}

_ROW_RE = re.compile(r"<tr\b[^>]*class=['\"][^'\"]*\bsubs-row\b[^'\"]*['\"][^>]*>(?P<body>.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td\b[^>]*>(?P<body>.*?)</td>", re.I | re.S)
_ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S)
_HREF_RE = re.compile(r"\bhref=['\"](?P<href>[^'\"]+)['\"]", re.I)
_MOUSEOVER_RE = re.compile(r"\bonMouseover=['\"](?P<value>[^'\"]+)['\"]", re.I)
_TITLE_RE = re.compile(
    r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)(?:\s*\[(?P<season>\d+)x(?P<episode>\d+)\])?",
    re.I,
)
_TITLE_EPISODE_RE = re.compile(r"(?:^|[\s._-])(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?:\b|$)", re.I)
_IMDB_RE = re.compile(r"imdb\.com/title/(?P<imdb>tt\d+)/?", re.I)
_RATING_RE = re.compile(r"(?:alt|title)=['\"]Rating:\s*(?P<rating>[\d.]+)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


def parse_search_results(body):
    text = _decode_html(body)
    rows = []
    for match in _ROW_RE.finditer(text):
        row = match.group("body")
        cells = [cell.group("body") for cell in _CELL_RE.finditer(row)]
        title_cell = next((cell for cell in cells if "c2field" in cell or "act=download" in cell), "")
        anchor = _download_anchor(title_cell)
        if not anchor:
            continue
        title_text = _strip_tags(title_cell)
        title_match = _TITLE_RE.search(title_text)
        if not title_match:
            continue
        title, season, episode = _title_and_episode_from_match(title_match)
        language = _language_from_cell(cells[5] if len(cells) > 5 else "")
        if not language:
            continue
        imdb_match = _IMDB_RE.search(row)
        rating_match = _RATING_RE.search(row)
        rows.append(
            {
                "download_url": _clean_download_url(anchor["href"]),
                "title": title,
                "year": int(title_match.group("year")),
                "season": season,
                "episode": episode,
                "language": language,
                "num_cds": _parse_int(cells[6] if len(cells) > 6 else ""),
                "fps": _parse_float(cells[7] if len(cells) > 7 else ""),
                "uploader": _strip_tags(cells[8] if len(cells) > 8 else "") or None,
                "imdb_id": imdb_match.group("imdb") if imdb_match else None,
                "rating": _parse_float(rating_match.group("rating") if rating_match else ""),
                "notes": _notes_from_anchor(anchor.get("attrs") or ""),
            }
        )
    return rows


def extract_archive_files(body):
    # Enumerate zip members cheaply for search-time scoring and episode filtering. RAR
    # archives are not opened worker-side anymore: the host extracts them at download time.
    if not body:
        return []
    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as archive:
            pairs = []
            for name in sorted(archive.namelist()):
                if _subtitle_extension(name):
                    pairs.append((name, archive.read(name)))
            return _archive_rows_from_pairs(pairs)
    return []


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
        if video.get("series_imdb_id") and item.get("imdb_id") == video.get("series_imdb_id"):
            matches.append("series_imdb_id")
    else:
        if _title_matches(video.get("title"), item.get("title")):
            matches.append("title")
        if video.get("year") and item.get("year") and int(video.get("year")) == int(item.get("year")):
            matches.append("year")
        if video.get("imdb_id") and item.get("imdb_id") == video.get("imdb_id"):
            matches.append("imdb_id")
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


class SubsSabBzProvider:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        request = urllib.request.Request(url, headers=_headers(referer))
        return self._open_request(request, timeout)

    def _http_post(self, url, data, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers = _headers(referer)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        return self._open_request(request, timeout)

    def _open_request(self, request, timeout):
        failures = 0
        while True:
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                failures += 1
                if error.code != 403 or failures >= 3:
                    raise
                error.close()
                time.sleep(10)

    def search(self, video, languages, config):
        video = dict(video or {})
        requested = _requested_languages(languages)
        if not requested:
            return []
        if video.get("kind") == "episode":
            if not video.get("series") or video.get("season") is None or video.get("episode") is None:
                return []
            media_type = "episode"
            title = _alias_title(video["series"], TV_NAME_FIXES)
        elif video.get("kind") == "movie":
            if not video.get("title"):
                return []
            media_type = "movie"
            title = _alias_title(video["title"], MOVIE_NAME_FIXES)
        else:
            return []
        match_video = dict(video)
        if media_type == "episode":
            match_video["series"] = title
        else:
            match_video["title"] = title

        config = dict(config or {})
        results = []
        seen = set()
        for alpha3, variants in requested.items():
            _sleep(config)
            rows = parse_search_results(self._http_post(SEARCH_URL, _search_payload(video, title, alpha3), referer=BASE_URL + "/"))
            for row in rows[:25]:
                if row["language"] != alpha3 or not _row_matches_video(row, match_video, media_type):
                    continue
                _sleep(config)
                try:
                    archive_files = extract_archive_files(self._http_get(row["download_url"], referer=SEARCH_URL))
                except Exception:
                    continue
                for archive_file in archive_files:
                    if not _file_matches_video(archive_file["filename"], video, media_type):
                        continue
                    for variant in variants:
                        item = {
                            **row,
                            **archive_file,
                            "media_type": media_type,
                            "language": variant,
                        }
                        key = (row["download_url"], archive_file["filename"], variant["alpha3"], variant["hi"], variant["forced"])
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(self._result(match_video, item))
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _result(self, video, item):
        language = item["language"]
        matches = derive_matches(video, item)
        score = 35
        for match_name, value in (
            ("title", 20),
            ("series", 20),
            ("year", 10),
            ("season", 12),
            ("episode", 15),
            ("imdb_id", 15),
            ("series_imdb_id", 15),
            ("release_group", 7),
            ("source", 5),
            ("resolution", 4),
            ("fps", 4),
        ):
            if match_name in matches:
                score += value
        season, episode = _payload_season_episode(item)
        payload = {
            "provider": PROVIDER_ID,
            "schema": 1,
            "download_url": item["download_url"],
            "filename": item["filename"],
            "title": item.get("title"),
            "year": item.get("year"),
            "season": season,
            "episode": episode,
            "language": language["alpha3"],
            "hi": language["hi"],
            "forced": language["forced"],
            "media_type": item.get("media_type"),
            "imdb_id": item.get("imdb_id"),
            "fps": item.get("fps"),
            "num_cds": item.get("num_cds"),
            "release_info": item["filename"],
        }
        return {
            "provider": PROVIDER_ID,
            "id": f"subssabbz-{_result_id(item, language)}",
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
            "page_link": item["download_url"],
            "display": {
                "source": "subs.sab.bz",
                "title": item.get("title"),
                "release": item["filename"],
                "uploader": item.get("uploader"),
            },
            "provider_payload": payload,
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        url = payload.get("download_url")
        if not url:
            raise ValueError("subssabbz download requires download_url")
        body = self._http_get(url, timeout=30, referer=SEARCH_URL)
        return _download_payload(body, payload)


def _download_payload(body, payload):
    payload = payload or {}
    # Reject broken responses up front: the download endpoint can answer with an empty
    # stream or an HTML/error page that would otherwise look like a successful download.
    if not body or not body.strip():
        raise ValueError(f"subssabbz empty download for {payload.get('download_url')}")
    if _is_html_body(body):
        raise ValueError(f"subssabbz returned an HTML/error page for {payload.get('download_url')}")
    if _is_archive_body(body):
        # Host-side extraction (Provider Hub v1.1+): hand the raw archive bytes back to
        # the host. Search emits one result per archive member and stores that member's
        # exact filename in the payload, so when we can list a zip we pin that member.
        # The host then reads the named member and runs chardet. RAR is not stdlib-listable
        # and a lone/ambiguous member is left to the host's episode pick.
        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        member = _select_zip_member(body, payload)
        if member is not None:
            archive["member"] = member
        else:
            archive["episode"] = payload.get("episode")
        return archive
    # Direct, non-archive subtitle body.
    return _content_payload(_normalize_line_endings(body), _format_from_filename(payload.get("filename")))


def _is_archive_body(body):
    return _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _select_zip_member(body, payload):
    # Reproduce the pre-migration select_subtitle_file: pin the exact member that search
    # scored (payload["filename"]), else break the tie with release_info token overlap.
    # Listing only, no extraction or decoding. Returns None for rar (not stdlib-listable),
    # a single member, or when nothing breaks the tie, so the caller defers to the host's
    # episode selection (which fails loudly on a true no-match, unlike a wrong member pin).
    payload = payload or {}
    if _is_rar_archive(body) or not zipfile.is_zipfile(io.BytesIO(body or b"")):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and _subtitle_extension(name)
            and not name.rsplit("/", 1)[-1].startswith(".")
        ]
    if len(members) < 2:
        return None  # a lone member: the host's episode pick already lands here
    # Strongest signal: the exact member filename search picked for this result.
    wanted = _normalize_member_path(payload.get("filename"))
    if wanted:
        exact = [name for name in members if _normalize_member_path(name) == wanted]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return None  # duplicate names cannot be told apart; defer to the host
    # Narrow to the requested season+episode before scoring so a multi-episode pack does
    # not let release tags from another episode win the tie.
    season = _parse_int_value(payload.get("season"))
    episode = _parse_int_value(payload.get("episode"))
    forced = bool(payload.get("forced"))
    pool = members
    if episode is not None:
        episode_pool = [name for name in members if _member_has_episode(name, season, episode)]
        if not episode_pool:
            # Episode requested but absent from every member: pinning a member from another
            # episode would hard-fail the host download, so defer to host episode selection.
            return None
        if not forced:
            # Drop foreign-parts-only members before the single-match shortcut below so a
            # non-forced request can never be pinned to a forced track. The release scorer
            # already penalizes them, but the len==1 shortcut returns before scoring runs.
            non_forced = [name for name in episode_pool if not _member_is_forced(name)]
            if not non_forced:
                # Only forced members carry this episode: defer to the host rather than
                # silently delivering a foreign-parts-only track for a non-forced request.
                return None
            episode_pool = non_forced
        if len(episode_pool) == 1:
            # A unique season+episode member. Pin it rather than deferring: the host's
            # episode-only pick could otherwise cross seasons in a pack that repeats the
            # episode number (S01E05 vs S02E05).
            return episode_pool[0]
        pool = episode_pool
    if len(pool) < 2:
        return None  # nothing left to disambiguate; let the host pick by episode
    # Break the tie with the same release_info tokens the pre-migration scorer used.
    release_info = _normalize_release(payload.get("release_info") or payload.get("filename"))
    best, best_score, tied = None, 0, False
    for name in pool:
        score = _member_release_score(name, release_info, forced=forced)
        if score > best_score:
            best, best_score, tied = name, score, False
        elif score == best_score and best is not None:
            tied = True
    if best is None or best_score == 0 or tied:
        return None  # cannot confidently disambiguate; let the host pick by episode
    return best


def _member_has_episode(name, season, episode):
    # Match SxxExx as a delimited token tolerating a separator between the season and
    # episode parts (S01E02, S01.E02, S01 E02, S01-E02), the NxNN form (1x02), and a
    # whole-token "{season}{episode:02d}" code (e.g. "102"). The (?!\d) / (?<!\d) guards
    # stop a 3-digit release tag from matching a substring ("720p", "x264").
    text = _normalize_release(name)
    if episode is None:
        return False
    if season is not None:
        if re.search(rf"(?<!\d)s0*{season}[\s._-]*e0*{episode}(?!\d)", text):
            return True
        if re.search(rf"(?<!\d){season}x0*{episode}(?!\d)", text):
            return True
        # Contiguous "{season}{episode:02d}" code, e.g. "102". Require non-alnum
        # delimiters so a release tag like "720p" / "x264" cannot match a substring.
        if re.search(rf"(?<![a-z0-9]){season}{episode:02d}(?![a-z0-9])", text):
            return True
        return False
    # No season known: only the episode-bearing forms we can anchor unambiguously.
    if re.search(rf"(?<!\d)s\d{{1,2}}[\s._-]*e0*{episode}(?!\d)", text):
        return True
    if re.search(rf"(?<!\d)\d{{1,2}}x0*{episode}(?!\d)", text):
        return True
    return False


def _member_release_score(name, release_info, forced=False):
    # Mirror the pre-migration scorer: count release_info tokens longer than two chars that
    # appear in the member name, then nudge .srt ahead of .sub on a tie. A member carrying a
    # delimited "forced" token is a foreign-parts-only track: heavily penalize it for a
    # non-forced request so the host never silently pins it (mirrors providers/titulky and
    # providers/subtitrarinoi). A forced request keeps the forced member in play.
    normalized = _normalize_release(name)
    score = 0
    if release_info:
        for token in (part for part in release_info.split(".") if len(part) > 2):
            if token in normalized:
                score += 4
    if name.lower().endswith(".srt"):
        score += 1
    if not forced and _member_is_forced(name):
        # Drive the score below the initial best_score (0) so a forced member can never win
        # the tie for a non-forced request; a forced-only pool then defers to host selection.
        score -= 1000
    return score


def _member_is_forced(name):
    # A delimited "forced" token on the member basename marks a foreign-parts-only track.
    # Match it as a whole token so "enforced"/"unforced" never trip the penalty.
    basename = _normalize_member_path(name).rsplit("/", 1)[-1]
    return "forced" in _normalize_release(basename).split(".")


def _parse_int_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_id(item, language):
    # Include hi/forced so same-language variants for one member do not collapse to one id.
    parts = (
        item["download_url"],
        item["filename"],
        language["alpha3"],
        "1" if language["hi"] else "0",
        "1" if language["forced"] else "0",
    )
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


def _payload_season_episode(item):
    # Host-side member selection keys off episode. Prefer the marker on the member
    # filename, fall back to the row-level season/episode. Movies carry no episode.
    if item.get("media_type") == "movie":
        return None, None
    season, episode = _season_episode_from_filename(item.get("filename"))
    if episode is None:
        episode = _episode_from_numeric_filename(item.get("filename"))
    if season is None:
        season = item.get("season")
    if episode is None:
        episode = item.get("episode")
    return season, episode


def _archive_rows_from_pairs(pairs):
    rows = []
    for filename, content in pairs:
        if _subtitle_extension(filename):
            rows.append({"filename": _normalize_member_path(filename), "content": content})
    return rows


def _normalize_member_path(filename):
    # Keep the directory so multi-CD packs like CD1/sub.srt and CD2/sub.srt stay distinct,
    # but normalize separators so the same member resolves identically at download time.
    return str(filename or "").replace("\\", "/").lstrip("/")


def _download_anchor(title_cell):
    for anchor in _ANCHOR_RE.finditer(title_cell or ""):
        attrs = anchor.group("attrs")
        href_match = _HREF_RE.search(attrs)
        if not href_match:
            continue
        href = html.unescape(href_match.group("href"))
        if "act=download" not in href:
            continue
        return {"href": href, "attrs": attrs, "text": _strip_tags(anchor.group("body"))}
    return None


def _clean_download_url(url):
    parsed = urllib.parse.urlparse(html.unescape(url or ""))
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if key != "s"]
    return urllib.parse.urlunparse(
        (
            parsed.scheme or "http",
            parsed.netloc or "subs.sab.bz",
            parsed.path or "/index.php",
            "",
            urllib.parse.urlencode(query),
            "",
        )
    )


def _notes_from_anchor(attrs):
    match = _MOUSEOVER_RE.search(attrs or "")
    if not match:
        return ""
    value = html.unescape(match.group("value"))
    return _strip_tags(value.replace("\\'", "'"))


def _language_from_cell(value):
    text = _strip_tags(value).lower()
    if "english" in text or text == "eng":
        return "eng"
    if "български" in text or "bulgarian" in text:
        return "bul"
    return None


def _title_and_episode_from_match(title_match):
    title = title_match.group("title").strip()
    season = int(title_match.group("season")) if title_match.group("season") else None
    episode = int(title_match.group("episode")) if title_match.group("episode") else None
    marker = _TITLE_EPISODE_RE.search(title)
    if marker:
        season = int(marker.group("season"))
        episode = int(marker.group("episode"))
        title = title[: marker.start()].strip(" .-_")
    return title, season, episode


def _row_matches_video(row, video, media_type):
    video_imdb_id = video.get("imdb_id") if media_type == "movie" else video.get("series_imdb_id")
    row_imdb_id = row.get("imdb_id")
    if video_imdb_id and row_imdb_id and video_imdb_id != row_imdb_id:
        return False
    if media_type == "movie":
        if not _title_matches(video.get("title"), row.get("title")):
            return False
        return not video.get("year") or row.get("year") == int(video.get("year"))
    if not _title_matches(video.get("series"), row.get("title")):
        return False
    if row.get("season") is not None and int(video.get("season")) != row["season"]:
        return False
    return not (row.get("episode") is not None and int(video.get("episode")) != row["episode"])


def _file_matches_video(filename, video, media_type):
    if media_type == "movie":
        return True
    season, episode = _season_episode_from_filename(filename)
    if season is None or episode is None:
        episode = _episode_from_numeric_filename(filename)
        if episode is None:
            return True
        return episode == int(video.get("episode"))
    return season == int(video.get("season")) and episode == int(video.get("episode"))


def _season_episode_from_filename(filename):
    normalized = _normalize_release(filename)
    match = re.search(r"s(?P<season>\d{1,2})e(?P<episode>\d{1,3})", normalized)
    if match:
        return int(match.group("season")), int(match.group("episode"))
    match = re.search(r"(?P<season>\d{1,2})x(?P<episode>\d{1,3})", normalized)
    if match:
        return int(match.group("season")), int(match.group("episode"))
    return None, None


def _episode_from_numeric_filename(filename):
    base = os.path.splitext(os.path.basename(str(filename or "")))[0]
    if re.fullmatch(r"\d{1,3}", base):
        return int(base)
    return None


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
        "act": "search",
        "movie": _query_title(title),
        "select-language": "1" if alpha3 == "eng" else "2",
        "upldr": "",
        "yr": "",
        "release": "",
    }
    if (video or {}).get("kind") == "movie" and (video or {}).get("year"):
        payload["yr"] = int(video["year"])
    return payload


def _alias_title(title, replacements):
    value = str(title or "")
    for old, new in replacements.items():
        if value == old or value.startswith(old):
            value = value.replace(old, new, 1)
            break
    return value


def _query_title(title):
    return _ascii_fold(title).replace("'", "")


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


def _is_rar_archive(body):
    return bool(body) and (body.startswith(b"Rar!\x1a\x07\x00") or body.startswith(b"Rar!\x1a\x07\x01\x00"))


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


def _format_from_filename(filename):
    return _subtitle_extension(filename or "") or "srt"


def _normalize_line_endings(content):
    return (content or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


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
    return "text/plain" if subtitle_format == "sub" else "application/x-subrip"


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
