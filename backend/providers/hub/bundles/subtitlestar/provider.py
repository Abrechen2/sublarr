"""SubtitleStar provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import io
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser

PROVIDER_ID = "subtitlestar"
BASE_URL = "https://subtitlestar.com"
DOWNLOAD_BASE_URL = "https://dl2.subtitlestar.com/dlsub"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
HTTP_TIMEOUT_SECONDS = 15
SUPPORTED_ALPHA3 = "fas"
SUPPORTED_ALPHA2 = "fa"
MAX_CANDIDATES_PER_QUERY = 8
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub", ".vtt")


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
        queries = []

        def add_query(value):
            value = value.strip()
            if value and value not in queries:
                queries.append(value)

        year = video.get("year")
        if year:
            add_query(f"{title} {year}")
        add_query(title)
        if ":" in title:
            short_title = title.split(":", 1)[0].strip()
            if short_title:
                if year:
                    add_query(f"{short_title} {year}")
                add_query(short_title)
        return queries
    if kind == "episode":
        series = (_coerce_text(video.get("series")) or "").strip()
        if not series:
            return []
        return [series]
    return []


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_tags(fragment):
    text = _TAG_RE.sub("", fragment or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


_SEARCH_RESULT_RE = re.compile(
    r"""<a[^>]+href=["'](https://subtitlestar\.com/persian-subtitles-[^"']+)["'][^>]*>"""
    r"""[^<]*<img[^>]+alt=["']([^"']*)["']""",
    re.IGNORECASE | re.DOTALL,
)

_SEARCH_RESULT_ALT_RE = re.compile(
    r"""<a[^>]+href=["'](https://subtitlestar\.com/persian-subtitles-[^"']+)["'][^>]*>"""
    r'\s*<h2[^>]*>([^<]+)</h2>',
    re.IGNORECASE | re.DOTALL,
)


def parse_search_results(html_bytes):
    if not html_bytes:
        return []
    text = html_bytes.decode("utf-8", errors="replace")
    results = []
    seen = set()
    
    for match in _SEARCH_RESULT_RE.finditer(text):
        url = match.group(1)
        title = match.group(2)
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "detail_url": url,
            "title": title,
        })
    
    for match in _SEARCH_RESULT_ALT_RE.finditer(text):
        url = match.group(1)
        title = _strip_tags(match.group(2))
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "detail_url": url,
            "title": title,
        })
    
    return results


_TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE | re.DOTALL)
_IMDB_RE = re.compile(r'imdb\.com/title/(tt\d+)', re.IGNORECASE)
_YEAR_RE = re.compile(r'icon-years[^>]*>.*?<a[^>]*>(\d{4})</a>', re.IGNORECASE | re.DOTALL)
_QUALITY_RE = re.compile(r'<b>کیفیت\s*:</b>([^<]+)</span>', re.IGNORECASE | re.DOTALL)
_DOWNLOAD_EXTENSIONS = (".zip", ".srt", ".ass", ".ssa", ".sub", ".vtt")
_UNSUPPORTED_ARCHIVE_EXTENSIONS = (".rar", ".7z")


class _DownloadLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.downloads = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        href = attrs_dict.get("href", "")
        if not _is_download_href(href, attrs_dict):
            return
        url = _normalize_download_url(href)
        if url and url not in self.downloads:
            self.downloads.append(url)


def _is_download_href(href, attrs):
    if not href:
        return False
    lowered = href.lower()
    parsed = urllib.parse.urlparse(lowered)
    path = parsed.path.lower()
    if (
        "trailer" in lowered
        or path.endswith((".mp4", ".mkv"))
        or path.endswith(_UNSUPPORTED_ARCHIVE_EXTENSIONS)
    ):
        return False

    host = parsed.netloc.lower()
    if host in {"dl.subtitlestar.com", "dl2.subtitlestar.com"}:
        return "/dlsub/" in path and path.endswith(_DOWNLOAD_EXTENSIONS)
    if not host:
        return path.startswith("/dlsub/") or path.endswith(_DOWNLOAD_EXTENSIONS)
    return False


def _normalize_download_url(url):
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/dlsub/"):
        return urllib.parse.urljoin(f"{DOWNLOAD_BASE_URL}/", url)
    if url.startswith("/"):
        return urllib.parse.urljoin(BASE_URL, url)
    if url.lower().startswith("dlsub/"):
        remainder = url.split("/", 1)[1].lstrip("/")
        return urllib.parse.urljoin(
            f"{DOWNLOAD_BASE_URL.rsplit('/dlsub', 1)[0]}/",
            f"dlsub/{remainder}",
        )
    return urllib.parse.urljoin(f"{DOWNLOAD_BASE_URL}/", url)


def parse_detail_page(html_bytes):
    if not html_bytes:
        return None
    text = html_bytes.decode("utf-8", errors="replace")
    
    title_match = _TITLE_RE.search(text)
    page_title = _strip_tags(title_match.group(1)) if title_match else ""
    
    imdb_match = _IMDB_RE.search(text)
    imdb_id = imdb_match.group(1) if imdb_match else None
    
    year_match = _YEAR_RE.search(text)
    year = year_match.group(1) if year_match else None
    
    quality_match = _QUALITY_RE.search(text)
    quality = _strip_tags(quality_match.group(1)) if quality_match else None
    
    parser = _DownloadLinkParser()
    parser.feed(text)
    
    return {
        "title": page_title,
        "imdb_id": imdb_id,
        "year": year,
        "quality": quality,
        "downloads": parser.downloads,
    }


def _normalize(text):
    return re.sub(r"[\W_]+", " ", (_coerce_text(text) or "").lower()).strip()


def _season_episode_markers(text):
    text = (_coerce_text(text) or "").lower()
    markers = []
    for marker in re.finditer(
        r"\bs0*(\d{1,2})((?:[\s._-]*e0*\d{1,3})+)",
        text,
    ):
        season = int(marker.group(1))
        for episode in re.findall(r"e0*(\d{1,3})", marker.group(2)):
            markers.append((season, int(episode)))
    for marker in re.finditer(r"\b0*(\d{1,2})x0*(\d{1,3})(?!\d)", text):
        season_episode = (int(marker.group(1)), int(marker.group(2)))
        if season_episode not in markers:
            markers.append(season_episode)
    for pattern in (
        r"\bs0*(\d{1,2})[\s._-]+ep(?:isode)?[\s._-]*0*(\d{1,3})(?!\d)",
        r"\bseason[\s._-]*0*(\d{1,2})[\s._-]+(?:ep|episode)[\s._-]*0*(\d{1,3})(?!\d)",
    ):
        for marker in re.finditer(pattern, text):
            season_episode = (int(marker.group(1)), int(marker.group(2)))
            if season_episode not in markers:
                markers.append(season_episode)
    return markers


def _season_episode_marker(text):
    markers = _season_episode_markers(text)
    return markers[0] if markers else None


def _episode_range_includes(text, episode, season=None):
    try:
        episode_int = int(episode)
    except (TypeError, ValueError):
        return False
    try:
        season_int = int(season)
    except (TypeError, ValueError):
        season_int = None
    text = (_coerce_text(text) or "").lower()
    saw_season_range = False
    for pattern in (
        r"\bs0*(?P<season>\d{1,2})e0*(?P<start>\d{1,3})\s*(?:-|to|through|thru)\s*(?:s0*(?P<end_season>\d{1,2})[\s._-]*)?e?0*(?P<end>\d{1,3})(?!\d)",
        r"\bs0*(?P<season>\d{1,2})[\s._-]+e0*(?P<start>\d{1,3})\s*(?:-|to|through|thru)\s*(?:s0*(?P<end_season>\d{1,2})[\s._-]*)?e?0*(?P<end>\d{1,3})(?!\d)",
    ):
        for marker in re.finditer(pattern, text):
            saw_season_range = True
            marker_season = int(marker.group("season"))
            end_season = marker.group("end_season")
            if end_season and int(end_season) != marker_season:
                continue
            if season_int is not None and marker_season != season_int:
                continue
            start = int(marker.group("start"))
            end = int(marker.group("end"))
            lower, upper = sorted((start, end))
            if lower <= episode_int <= upper:
                return True
    if saw_season_range:
        return False
    for marker in re.finditer(
        r"\be0*(\d{1,3})\s*(?:-|to|through|thru)\s*e?0*(\d{1,3})(?!\d)",
        text,
    ):
        explicit_seasons = _explicit_season_numbers(text)
        if season_int is not None and explicit_seasons and season_int not in explicit_seasons:
            continue
        start = int(marker.group(1))
        end = int(marker.group(2))
        lower, upper = sorted((start, end))
        if lower <= episode_int <= upper:
            return True
    return False


def _explicit_season_numbers(text):
    text = (_coerce_text(text) or "").lower()
    seasons = set()
    for pattern in (
        r"\bs0*(\d{1,2})(?=e\d{1,3}(?!\d))",
        r"\bs0*(\d{1,2})(?=[\s._-]+e\d{1,3}(?!\d))",
        r"\b0*(\d{1,2})(?=x\d{1,3}(?!\d))",
        r"\bseason\s*0*(\d{1,2})(?!\d)",
        r"\bs0*(\d{1,2})(?!\d)",
    ):
        for marker in re.finditer(pattern, text):
            seasons.add(int(marker.group(1)))
    return seasons


def _episode_marker_matches(text, episode):
    text = (_coerce_text(text) or "").lower()
    return bool(re.search(rf"\be0*{int(episode)}(?!\d)", text))


def _explicit_episode_numbers(text):
    text = (_coerce_text(text) or "").lower()
    episodes = set()
    for _, episode in _season_episode_markers(text):
        episodes.add(episode)
    for pattern in (
        r"\be0*(\d{1,3})(?!\d)",
    ):
        for marker in re.finditer(pattern, text):
            episodes.add(int(marker.group(1)))
    return episodes


def _year_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _candidate_years(candidate_title, title=None):
    years = {
        int(year)
        for year in re.findall(r"\b(?:19|20)\d{2}\b", _coerce_text(candidate_title) or "")
    }
    title_years = {
        int(year)
        for year in re.findall(r"\b(?:19|20)\d{2}\b", _coerce_text(title) or "")
    }
    return years - title_years


def compute_score(video, candidate_title):
    video = video or {}
    kind = video.get("kind")
    candidate_text = _coerce_text(candidate_title) or ""
    candidate_norm = _normalize(candidate_text)
    candidate_tokens = set(candidate_norm.split())
    
    if kind == "movie":
        title = _normalize(video.get("title"))
        title_tokens = set(title.split()) if title else set()
        if title_tokens and title_tokens.issubset(candidate_tokens):
            year = _year_int(video.get("year"))
            if year and str(year) in candidate_tokens:
                return 100
            # Check if candidate has a conflicting year (e.g., Dune 1984 vs Dune 2021)
            if year:
                # Look for 4-digit years in candidate that don't match requested year
                years = _candidate_years(candidate_title, video.get("title"))
                if years:
                    # If candidate has explicit years and none match requested year, demote
                    if year not in years:
                        return 60
            return 90
        return 60
    
    if kind == "episode":
        series = _normalize(video.get("series"))
        series_tokens = set(series.split()) if series else set()
        if series_tokens and series_tokens.issubset(candidate_tokens):
            season = video.get("season")
            episode = video.get("episode")
            # Require episode marker for high score
            if season is not None and episode is not None:
                markers = _season_episode_markers(candidate_text)
                if any(marker == (int(season), int(episode)) for marker in markers):
                    return 95
                if _episode_range_includes(candidate_text, episode, season):
                    return 95
            return 85
        return 60
    
    return 60


def derive_matches(video, candidate_title):
    video = video or {}
    kind = video.get("kind")
    candidate_text = _coerce_text(candidate_title) or ""
    candidate_norm = _normalize(candidate_text)
    candidate_tokens = set(candidate_norm.split())
    matches = []
    
    if kind == "movie":
        title = _normalize(video.get("title"))
        title_tokens = set(title.split()) if title else set()
        if title_tokens and title_tokens.issubset(candidate_tokens):
            matches.append("title")
        year = video.get("year")
        if year and str(year) in candidate_tokens:
            matches.append("year")
    elif kind == "episode":
        series = _normalize(video.get("series"))
        series_tokens = set(series.split()) if series else set()
        if series_tokens and series_tokens.issubset(candidate_tokens):
            matches.append("series")
        season = video.get("season")
        if season is not None:
            if int(season) in _explicit_season_numbers(candidate_norm):
                matches.append("season")
        episode = video.get("episode")
        if episode is not None:
            markers = _season_episode_markers(candidate_text)
            if markers:
                if any(
                    marker_episode == int(episode)
                    and (season is None or marker_season == int(season))
                    for marker_season, marker_episode in markers
                ):
                    matches.append("episode")
                elif _episode_range_includes(candidate_text, episode, season):
                    matches.append("episode")
            elif _episode_range_includes(candidate_text, episode, season):
                matches.append("episode")
            elif _episode_marker_matches(candidate_text, episode):
                explicit_seasons = _explicit_season_numbers(candidate_text)
                if season is None or not explicit_seasons or int(season) in explicit_seasons:
                    matches.append("episode")
    
    return matches


def _normalize_imdb_id(value):
    text = (_coerce_text(value) or "").strip().lower()
    if not text:
        return ""
    match = re.search(r"tt\d+", text)
    if match:
        return match.group(0)
    digits = re.sub(r"\D+", "", text)
    return f"tt{digits}" if digits else ""


def _detail_imdb_matches(video, details):
    if (video or {}).get("kind") != "movie":
        return False
    requested = _normalize_imdb_id((video or {}).get("imdb_id"))
    found = _normalize_imdb_id((details or {}).get("imdb_id"))
    return bool(requested and found and requested == found)


def _has_required_match(video, matches, candidate_title=None):
    video = video or {}
    matches = set(matches or [])
    if video.get("kind") == "movie":
        if "imdb_id" in matches:
            return True
        if "title" not in matches:
            return False
        requested_year = _year_int(video.get("year"))
        if requested_year and "year" not in matches:
            candidate_years = _candidate_years(candidate_title, video.get("title"))
            if candidate_years:
                return False
            if not candidate_title:
                return False
    elif video.get("kind") == "episode":
        if video.get("series") and "series" not in matches:
            return False
        if video.get("episode") is not None and "episode" not in matches:
            if candidate_title and _explicit_episode_numbers(candidate_title):
                return False
            return "season" in matches
    return True


def _is_archive_sidecar(name):
    path = (name or "").replace("\\", "/")
    parts = [part for part in path.split("/") if part]
    return "__MACOSX" in parts or os.path.basename(path).startswith("._")


def _is_paired_vobsub_sub(name, names):
    path = (name or "").replace("\\", "/").lower()
    if not path.endswith(".sub"):
        return False
    idx_path = f"{os.path.splitext(path)[0]}.idx"
    normalized_names = {
        (candidate or "").replace("\\", "/").lower()
        for candidate in names
    }
    return idx_path in normalized_names


def select_subtitle_file(names, video):
    return select_subtitle_files(names, video)[0]


def select_subtitle_files(names, video):
    candidates = [
        name
        for name in names
        if _subtitle_extension(name) and not _is_archive_sidecar(name)
        and not _is_paired_vobsub_sub(name, names)
    ]
    if not candidates:
        raise ValueError("subtitlestar archive contains no supported subtitle files")
    episode = (video or {}).get("episode")
    season = (video or {}).get("season")
    try:
        episode_int = int(episode)
    except (TypeError, ValueError):
        episode_int = None
    try:
        season_int = int(season)
    except (TypeError, ValueError):
        season_int = None
    
    if episode_int is None:
        if len(candidates) == 1:
            return candidates
        multipart = _multipart_subset(candidates)
        if multipart:
            return multipart
        return [candidates[0]]

    def score(name):
        normalized_name = name.lower()
        markers = _season_episode_markers(normalized_name)
        if markers:
            for marker_season, marker_episode in markers:
                if marker_episode != episode_int:
                    continue
                if season_int is not None and marker_season != season_int:
                    continue
                return 200 if season_int is not None else 100
            if _episode_range_includes(normalized_name, episode_int, season_int):
                return 200 if season_int is not None else 100
            return 0

        season_markers = _explicit_season_numbers(normalized_name)
        if season_int is not None and season_markers and season_int not in season_markers:
            return 0

        if _episode_range_includes(normalized_name, episode_int, season_int):
            return 100

        # Fallback: match episode number with E prefix and boundary
        if _episode_marker_matches(normalized_name, episode_int):
            return 100
        return 0

    # Score all candidates and find the best match
    scored = [(score(name), name) for name in candidates]
    best_score, best_name = max(scored, key=lambda x: x[0])
    
    # Reject if no episode match found
    if best_score == 0:
        if len(candidates) == 1:
            normalized_name = candidates[0].lower()
            if not _explicit_episode_numbers(normalized_name):
                season_markers = _explicit_season_numbers(normalized_name)
                if (
                    season_int is None
                    or not season_markers
                    or season_int in season_markers
                ):
                    return candidates
        raise ValueError(
            f"subtitlestar archive contains no subtitle matching episode {episode_int}"
        )

    matching_files = [name for score_value, name in scored if score_value == best_score]
    multipart = _multipart_subset(matching_files)
    if multipart:
        return multipart
    return [best_name]


def _part_index(name):
    normalized = _normalize(os.path.splitext(os.path.basename(name))[0])
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


def _subtitle_extension(name):
    path = urllib.parse.urlparse(name or "").path or (name or "")
    lowered = path.lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def extract_download(body, filename="", video=None):
    if not body:
        return _content_payload(b"", _format_from_filename(filename), empty=True)

    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as archive:
            names = archive.namelist()
            selected = select_subtitle_files(names, video or {})
            if len(selected) > 1:
                # A multipart subtitle (CD1/CD2 ...) cannot survive the single-member
                # host contract: pinning one member would silently drop the other discs.
                # Concatenate the parts worker-side (stdlib zip listing only) with the
                # same b"\n\n".join the pre-host worker used, and return direct content.
                subtitle_format = (
                    _subtitle_extension(selected[0])
                    or _format_from_filename(selected[0])
                )
                content = b"\n\n".join(archive.read(name) for name in selected)
                if not content:
                    return _content_payload(b"", subtitle_format, empty=True)
                return _content_payload(content, subtitle_format)
            member = selected[0]
        # Single-member host-side extraction (Provider Hub v1.1+): the member is the
        # confident episode/movie pick, so hand the raw archive bytes plus that member
        # name to the host, which extracts it and detects the encoding.
        return {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
            "member": member,
            "empty": False,
        }

    filename_path = urllib.parse.urlparse(filename or "").path.lower()
    subtitle_format = _subtitle_extension(filename)
    if filename_path.endswith(".zip") or not subtitle_format or _looks_like_html(body):
        raise ValueError("subtitlestar download did not return a subtitle payload")
    if (video or {}).get("kind") == "episode":
        select_subtitle_files([filename_path or filename], video or {})
    return _content_payload(body, subtitle_format)


def _format_from_filename(filename):
    extension = _subtitle_extension(filename or "")
    return extension or "srt"


def _content_payload(content, subtitle_format, empty=False):
    if empty:
        return {
            "content_b64": "",
            "content_sha256": "",
            "content_type": _content_type(subtitle_format),
            "format": subtitle_format,
            "empty": True,
        }
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
    return {
        "srt": "application/x-subrip",
        "ass": "text/x-ssa",
        "ssa": "text/x-ssa",
        "vtt": "text/vtt",
        "sub": "text/plain",
    }.get(subtitle_format, "text/plain")


def _looks_like_html(body):
    sample = (body or b"").lstrip()[:200].lower()
    return sample.startswith((b"<!doctype html", b"<html")) or b"<title" in sample


def _requested_persian_language(languages):
    for language in languages or []:
        if not isinstance(language, dict):
            continue
        alpha3 = (language.get("alpha3") or "").lower()
        alpha2 = (language.get("alpha2") or "").lower()
        if alpha3 == SUPPORTED_ALPHA3 or alpha2 == SUPPORTED_ALPHA2:
            return {
                "alpha3": SUPPORTED_ALPHA3,
                "alpha2": SUPPORTED_ALPHA2,
                "hi": False,
                "forced": False,
            }
    return None


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(int(delay_ms), 5000) / 1000.0)


def _filename_from_headers(headers):
    disposition = (headers or {}).get("content-disposition", "")
    match = re.search(r'filename\*?=(?:[^\'";]+\'\')?"?([^";]+)"?', disposition)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1)).strip()


def _download_basename(url):
    return os.path.basename(urllib.parse.urlparse(url or "").path)


def _candidate_scoring_title(video, candidate_title, details):
    scoring_title = _coerce_text(candidate_title) or ""
    detail_title = _coerce_text((details or {}).get("title")) or ""
    if detail_title:
        requested_title = video.get("title") if (video or {}).get("kind") == "movie" else video.get("series")
        requested_tokens = set(_normalize(requested_title).split())
        scoring_tokens = set(_normalize(scoring_title).split())
        if requested_tokens and not requested_tokens.issubset(scoring_tokens):
            scoring_title = detail_title
    if (details or {}).get("year"):
        scoring_title = f"{scoring_title} {details['year']}"
    return scoring_title


class SubtitlestarProvider:
    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "fa,en;q=0.8",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def search(self, video, languages, config):
        config = dict(config or {})
        language = _requested_persian_language(languages)
        if language is None:
            return []
        queries = build_queries(video)
        if not queries:
            return []

        results = []
        seen_urls = set()
        for query in queries:
            _sleep(config)
            search_url = f"{BASE_URL}/?s={urllib.parse.quote(query)}&post_type=post"
            body = self._http_get(search_url)
            
            candidates = parse_search_results(body)
            for candidate in candidates[:MAX_CANDIDATES_PER_QUERY]:
                if candidate["detail_url"] in seen_urls:
                    continue
                seen_urls.add(candidate["detail_url"])
                
                _sleep(config)
                try:
                    detail_body = self._http_get(candidate["detail_url"])
                except Exception:
                    continue
                
                details = parse_detail_page(detail_body)
                if not details or not details["downloads"]:
                    continue
                
                scoring_title = _candidate_scoring_title(
                    video,
                    candidate["title"],
                    details,
                )
                
                score = compute_score(video, scoring_title)
                matches = derive_matches(video, scoring_title)
                if _detail_imdb_matches(video, details):
                    matches.append("imdb_id")
                if not _has_required_match(video, matches, scoring_title):
                    continue
                
                for download_url in details["downloads"][:1]:
                    results.append({
                        "provider": PROVIDER_ID,
                        "id": f"subtitlestar-{hashlib.md5(download_url.encode()).hexdigest()[:12]}",
                        "language": language,
                        "release_info": f"{candidate['title']} {details['quality']}".strip() if details['quality'] else candidate['title'],
                        "filename": f"subtitlestar.{_download_basename(download_url)}",
                        "matches": matches,
                        "score": score,
                        "score_without_hash": score,
                        "score_out_of": 100,
                        "hash_verifiable": False,
                        "hearing_impaired_verifiable": False,
                        "hearing_impaired": False,
                        "page_link": candidate["detail_url"],
                        "display": {
                            "source": "subtitlestar.com",
                            "title": candidate["title"],
                            "quality": details["quality"],
                            "year": details["year"],
                        },
                        "provider_payload": {
                            "provider": PROVIDER_ID,
                            "schema": 1,
                            "download_url": download_url,
                            "detail_url": candidate["detail_url"],
                            "video": _video_payload(video),
                        },
                    })
            
            if results:
                break
        
        return sorted(results, key=lambda item: item.get("score", 0), reverse=True)

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        download_url = payload.get("download_url")
        if not download_url:
            raise ValueError("subtitlestar download requires download_url")
        
        body = self._http_get(download_url)
        filename = os.path.basename(urllib.parse.urlparse(download_url).path)
        return extract_download(
            body,
            filename=filename,
            video=payload.get("video") or {},
        )


def _video_payload(video):
    video = video or {}
    return {
        "kind": video.get("kind"),
        "title": video.get("title"),
        "series": video.get("series"),
        "year": video.get("year"),
        "season": video.get("season"),
        "episode": video.get("episode"),
    }
