"""Moviesubtitles.org provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
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

PROVIDER_ID = "moviesubtitles"
PUBLIC_BASE_URL = "https://www.moviesubtitles.org"
HTTP_TIMEOUT_SECONDS = 15
MAX_MOVIE_PAGES = 3
MAX_RESULTS = 25
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

LANGUAGES = {
    "ara": {"alpha2": "ar", "flag": "ar", "name": "arabic"},
    "deu": {"alpha2": "de", "flag": "de", "name": "german"},
    "ell": {"alpha2": "el", "flag": "gr", "name": "greek"},
    "eng": {"alpha2": "en", "flag": "en", "name": "english"},
    "fra": {"alpha2": "fr", "flag": "fr", "name": "french"},
    "hun": {"alpha2": "hu", "flag": "hu", "name": "hungarian"},
    "ita": {"alpha2": "it", "flag": "it", "name": "italian"},
    "pol": {"alpha2": "pl", "flag": "pl", "name": "polish"},
    "por": {"alpha2": "pt", "flag": "br", "name": "portuguese"},
    "rus": {"alpha2": "ru", "flag": "ru", "name": "russian"},
    "spa": {"alpha2": "es", "flag": "es", "name": "spanish"},
    "tur": {"alpha2": "tr", "flag": "tr", "name": "turkish"},
    "ukr": {"alpha2": "uk", "flag": "ua", "name": "ukrainian"},
}
_LANGUAGE_NAME_TO_ALPHA3 = {value["name"]: key for key, value in LANGUAGES.items()}
_ALPHA2_TO_ALPHA3 = {value["alpha2"]: key for key, value in LANGUAGES.items()}

_MOVIE_LINK_RE = re.compile(
    rb'<a\b[^>]*href=["\']/movie-(?P<id>\d+)\.html["\'][^>]*>(?P<title>.*?)</a>',
    re.I | re.S,
)
_SUBTITLE_LINK_RE = re.compile(
    rb'href=["\']/subtitle-(?P<id>\d+)\.html["\']\s+title=["\']Download (?P<language>[^"\']+) subtitles["\'].*?<b>(?P<title>.*?)</b>',
    re.I | re.S,
)
_TAG_RE = re.compile(rb"<[^>]+>")
_WS_BYTES_RE = re.compile(rb"\s+")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_YEAR_RE = re.compile(r"\((\d{4})\)")


def build_queries(video):
    video = video or {}
    if video.get("kind") != "movie":
        return []
    title = _coerce_text(video.get("title"))
    if not title:
        return []
    year = video.get("year")
    return [f"{title} {year}", title] if year else [title]


def parse_search_results(body):
    results = []
    seen = set()
    for match in _MOVIE_LINK_RE.finditer(body or b""):
        movie_id = _decode(match.group("id"))
        if movie_id in seen:
            continue
        title = _strip_tags(match.group("title"))
        seen.add(movie_id)
        results.append(
            {
                "movie_id": movie_id,
                "title": title,
                "year": _year_from_title(title),
                "url": f"{PUBLIC_BASE_URL}/movie-{movie_id}.html",
            }
        )
    return results


def parse_movie_subtitles(body):
    rows = []
    matches = list(_SUBTITLE_LINK_RE.finditer(body or b""))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body or b"")
        chunk = (body or b"")[start:end]
        language_name = _normalize_language_label(_decode(match.group("language")))
        alpha3 = _LANGUAGE_NAME_TO_ALPHA3.get(language_name)
        if not alpha3:
            continue
        subtitle_id = _decode(match.group("id"))
        title = _strip_tags(match.group("title"))
        rip = _meta_value(chunk, "Rip")
        release = _meta_value(chunk, "release")
        rows.append(
            {
                "subtitle_id": subtitle_id,
                "language": alpha3,
                "title": title,
                "rip": rip,
                "release": release,
                "release_info": " ".join(part for part in [title, rip, release] if part),
                "uploaded": _meta_value(chunk, "uploaded"),
                "size": _meta_value(chunk, "size"),
                "parts": _int_from_text(_meta_value(chunk, "parts")),
                "downloads": _int_from_text(_meta_value(chunk, "downloaded")),
                "page_url": f"{PUBLIC_BASE_URL}/subtitle-{subtitle_id}.html",
                "download_url": f"{PUBLIC_BASE_URL}/download-{subtitle_id}.html",
            }
        )
    return rows


def derive_matches(video, candidate_title):
    if not video:
        return []
    candidate_tokens = set(_tokens(candidate_title))
    matches = []
    title_tokens = _tokens(video.get("title"))
    if title_tokens and all(token in candidate_tokens for token in title_tokens):
        matches.append("title")
    year = video.get("year")
    if year and str(year) in candidate_tokens:
        matches.append("year")
    return matches


class MoviesubtitlesProvider:
    def _http_request(self, url, data=None, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        try:
            return _open_url(url, data=data, timeout=timeout, referer=referer)
        except urllib.error.HTTPError as error:
            body = _read_http_error_body(error)
            if error.code == 500 and body and _allows_legacy_500_body(url):
                return body
            raise

    def search(self, video, languages, config):
        if (video or {}).get("kind") != "movie":
            return []
        requested = [_alpha3_for_language(language) for language in languages or []]
        requested = [language for language in requested if language in LANGUAGES]
        if not requested:
            return []
        results = []
        seen = set()
        for query in build_queries(video):
            _sleep(config)
            post_body = urllib.parse.urlencode({"q": query}).encode("ascii")
            search_body = self._http_request(f"{PUBLIC_BASE_URL}/search.php", data=post_body)
            movie_pages = _rank_movie_pages(video, parse_search_results(search_body))
            for movie_page in movie_pages[:MAX_MOVIE_PAGES]:
                _sleep(config)
                rows = parse_movie_subtitles(self._http_request(movie_page["url"], referer=f"{PUBLIC_BASE_URL}/search.php"))
                for row in rows:
                    if row["language"] not in requested or not _row_matches_video(video, row, movie_page):
                        continue
                    key = (row["subtitle_id"], row["language"])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(self._result(video, movie_page, row))
                    if len(results) >= MAX_RESULTS:
                        return _sort_results(results)
                if results:
                    return _sort_results(results)
            if results:
                return _sort_results(results)
        return _sort_results(results)

    def _result(self, video, movie_page, row):
        language = LANGUAGES[row["language"]]
        candidate_title = f"{movie_page['title']} {row['release_info']}"
        matches = derive_matches(video, candidate_title)
        score = 95 if "year" in matches else 85
        filename = f"moviesubtitles.{_slug(row['release_info'])}.{language['alpha2']}.zip"
        return {
            "provider": PROVIDER_ID,
            "id": f"moviesubtitles-{row['subtitle_id']}-{row['language']}",
            "language": {
                "alpha3": row["language"],
                "alpha2": language["alpha2"],
                "hi": False,
                "forced": False,
            },
            "release_info": row["release_info"],
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": row["page_url"],
            "display": {
                "source": "moviesubtitles",
                "title": movie_page["title"],
                "release": row["release_info"],
                "size": row["size"],
                "downloads": row["downloads"],
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": row["subtitle_id"],
                "url": row["download_url"],
                "page_url": row["page_url"],
                "filename": filename,
                "language": row["language"],
            },
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        url = payload.get("url")
        if not url:
            raise ValueError("moviesubtitles download requires url")
        body = self._http_request(url, referer=payload.get("page_url"))
        return extract_download(body, payload)


def extract_download(body, payload=None):
    payload = payload or {}
    if not body or not body.strip():
        raise ValueError("moviesubtitles download returned an empty body")
    if _is_html_body(body):
        raise ValueError("moviesubtitles download did not return a supported subtitle file")
    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        # A multi-part subtitle (CD1/CD2 ...) has to be concatenated, which the single-member
        # host contract cannot do: pinning one member would deliver only one disc and silently
        # drop the rest. When the zip holds a multipart set, join those members worker-side
        # (stdlib listing only) and return direct content so the user gets the whole subtitle.
        multipart = _multipart_content(body)
        if multipart is not None:
            return multipart
        # Single member: list the zip cheaply with stdlib to pick the member, then hand the raw
        # archive bytes back. The host extracts that exact member and detects encoding via
        # Subtitle.normalize().
        with zipfile.ZipFile(stream) as archive:
            member = select_subtitle_file(archive.namelist())
        return _archive_payload(body, member=member)
    if _is_rar_archive(body) or _is_7z_archive(body):
        # RAR/7z are not stdlib-listable (and bundling rarfile/py7zz is banned), so even a
        # multipart rar falls back to the host's episode pick over the whole archive.
        return _archive_payload(body, episode=payload.get("episode"))
    subtitle_format = _subtitle_extension(payload.get("filename", ""))
    if not subtitle_format:
        raise ValueError("moviesubtitles download did not return a supported subtitle file")
    return _content_payload(body, subtitle_format)


def select_subtitle_file(names):
    return select_subtitle_files(names)[0]


def select_subtitle_files(names):
    candidates = _subtitle_candidates(names)
    if not candidates:
        raise ValueError("moviesubtitles archive contains no supported subtitle files")
    multipart = _multipart_subset(candidates)
    if multipart:
        return multipart
    return [_primary_subtitle_file(candidates)]


def _subtitle_candidates(names):
    # Drop directory entries and editor/OS sidecars (__MACOSX/._x.srt, .DS_Store) so a stray
    # resource fork never shadows the real subtitle in selection or multipart grouping.
    return [
        name
        for name in names
        if not name.endswith("/") and _subtitle_extension(name) and not _is_sidecar(name)
    ]


def _is_sidecar(name):
    parts = name.replace("\\", "/").split("/")
    if any(part == "__MACOSX" for part in parts):
        return True
    return os.path.basename(name).startswith(".")


def _open_url(url, data=None, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _read_http_error_body(error):
    try:
        return error.read()
    finally:
        error.close()


def _rank_movie_pages(video, pages):
    ranked = []
    wanted_tokens = _tokens((video or {}).get("title"))
    wanted_norm = _normalize((video or {}).get("title"))
    for index, page in enumerate(pages):
        title_without_year = _YEAR_RE.sub("", page["title"]).strip()
        page_tokens = set(_tokens(title_without_year))
        score = 0
        if wanted_tokens and all(token in page_tokens for token in wanted_tokens):
            score = 80
        if wanted_norm and _normalize(title_without_year) == wanted_norm:
            score = 110
        try:
            wanted_year = int((video or {}).get("year"))
        except (TypeError, ValueError):
            wanted_year = None
        if wanted_year is not None and page.get("year") == wanted_year:
            score += 10
        if score:
            ranked.append((page, score, index))
    ranked.sort(key=lambda item: (-item[1], item[2]))
    return [page for page, _score, _index in ranked]


def _row_matches_video(video, row, movie_page):
    matches = derive_matches(video, f"{movie_page['title']} {row['release_info']}")
    wanted_year = _safe_int((video or {}).get("year"))
    candidate_year = movie_page.get("year")
    if wanted_year is not None and candidate_year is not None and candidate_year != wanted_year:
        return False
    return "title" in matches


def _sort_results(results):
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _meta_value(chunk, label):
    pattern = re.compile(
        rb'alt=["\']' + re.escape(label.encode("utf-8")) + rb'["\']\s+title=["\']'
        + re.escape(label.encode("utf-8"))
        + rb'["\'][^>]*>\s*</td>\s*<td\b[^>]*>(?P<value>.*?)</td>',
        re.I | re.S,
    )
    match = pattern.search(chunk or b"")
    return _strip_tags(match.group("value")) if match else ""


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    if alpha3:
        return alpha3
    return _ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())


def _normalize_language_label(label):
    normalized = (label or "").lower().strip()
    normalized = re.sub(r"\([^)]*\)", "", normalized).strip()
    if normalized == "portugese":
        return "portuguese"
    return normalized


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _archive_payload(body, member=None, episode=None):
    # Hand the raw archive bytes to the host (Provider Hub v1.1+). The host extracts the
    # member with its own zipfile/rarfile stack and detects encoding via normalize().
    payload = {
        "archive_b64": _base64.b64encode(body).decode("ascii"),
        "archive_sha256": _hashlib.sha256(body).hexdigest(),
    }
    if member is not None:
        payload["member"] = member
    else:
        payload["episode"] = episode
    return payload


def _multipart_content(body):
    # Concatenate a CD1/CD2-style multipart subtitle from a zip into one content payload.
    # Listing only (no host-banned rar/7z libs). Returns None when the archive holds no
    # multipart set, so the caller falls back to pinning a single member for the host.
    if _is_rar_archive(body) or not zipfile.is_zipfile(io.BytesIO(body)):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = _subtitle_candidates(archive.namelist())
        multipart = _multipart_subset(names)
        if not multipart:
            return None
        # Same order and b"\n\n" join the pre-migration worker used, so the rendered subtitle
        # is byte-for-byte what it produced before extraction moved to the host.
        content = b"\n\n".join(archive.read(name) for name in multipart)
    return _content_payload(content, _subtitle_extension(multipart[0]) or "srt")


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially latin-1, which never fails to decode) only reintroduces mojibake.
    return {
        "content_b64": _base64.b64encode(content).decode("ascii"),
        "content_sha256": _hashlib.sha256(content).hexdigest(),
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
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _year_from_title(title):
    match = _YEAR_RE.search(title or "")
    return int(match.group(1)) if match else None


def _int_from_text(text):
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _part_index(name):
    normalized = _normalize(os.path.basename(name))
    match = re.search(r"\b(?:cd|part|disc|disk)\s*0*(\d+)\b", normalized)
    return int(match.group(1)) if match else 0


def _multipart_subset(names):
    groups = {}
    for name in names:
        part_index = _part_index(name)
        if part_index <= 0:
            continue
        groups.setdefault((_multipart_key(name), _subtitle_extension(name)), []).append(name)
    valid_groups = []
    for group in groups.values():
        part_numbers = [_part_index(name) for name in group]
        if len(group) > 1 and len(set(part_numbers)) == len(part_numbers):
            valid_groups.append(group)
    if not valid_groups:
        return []
    best_group = max(valid_groups, key=lambda group: (len(group), -min(_part_index(name) for name in group)))
    return sorted(best_group, key=lambda name: (_part_index(name), name.lower()))


def _multipart_key(name):
    stem = os.path.splitext(os.path.basename(name))[0]
    normalized = _normalize(stem)
    return re.sub(r"\b(?:cd|part|disc|disk)\s*0*\d+\b", "", normalized).strip()


def _primary_subtitle_file(names):
    return sorted(enumerate(names), key=lambda item: (_variant_penalty(item[1]), _extension_priority(item[1]), item[0]))[0][1]


def _variant_penalty(name):
    tokens = set(_tokens(os.path.splitext(os.path.basename(name))[0]))
    if tokens & {"hi", "sdh", "forced", "commentary"}:
        return 1
    if {"hearing", "impaired"} <= tokens:
        return 1
    return 0


def _extension_priority(name):
    extension = _subtitle_extension(name)
    try:
        return ["srt", "ass", "ssa", "vtt", "sub"].index(extension)
    except ValueError:
        return len(SUBTITLE_EXTENSIONS)


def _is_html_body(body):
    sample = (body or b"").lstrip()[:512].lower()
    return sample.startswith((b"<!doctype html", b"<html")) or b"<title" in sample


def _is_rar_archive(body):
    return bool(body) and body[:4] == b"Rar!"


def _is_7z_archive(body):
    return bool(body) and body[:6] == b"7z\xbc\xaf\x27\x1c"


def _allows_legacy_500_body(url):
    path = urllib.parse.urlparse(url).path
    return path.endswith("/search.php") or re.search(r"/movie-\d+\.html$", path) is not None


def _strip_tags(value):
    stripped = _TAG_RE.sub(b"", value or b"")
    stripped = _WS_BYTES_RE.sub(b" ", stripped).strip()
    return _WS_RE.sub(" ", html.unescape(_decode(stripped))).strip()


def _tokens(value):
    return [token for token in _normalize(_coerce_text(value)).split(" ") if token]


def _normalize(value):
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _coerce_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        joined = " ".join(str(item) for item in value if item not in (None, ""))
        return joined or None
    return str(value)


def _slug(value):
    return "-".join(_tokens(value)) or "release"


def _decode(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")
