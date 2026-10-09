"""SubHD provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import functools
import hashlib as _hashlib
import html
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar

_PROVIDER_DIR = os.path.dirname(__file__)
if _PROVIDER_DIR and _PROVIDER_DIR not in sys.path:
    sys.path.insert(0, _PROVIDER_DIR)

from captcha_templates import CAPTCHA_TEMPLATE_ROWS

PROVIDER_ID = "subhd"
BASE_URL = "https://subhd.tv"
API_DOWN_URL = f"{BASE_URL}/api/sub/down"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
HTTP_TIMEOUT_SECONDS = 15
MAX_CANDIDATES_PER_QUERY = 12
MAX_CAPTCHA_ATTEMPTS = 6
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")


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
        return [f"{series} {tag}", series]
    if kind == "movie":
        title = (_coerce_text(video.get("title")) or "").strip()
        if not title:
            return []
        year = video.get("year")
        if year:
            return [f"{title} {year}", title]
        return [title]
    return []


_TAG_RE = re.compile(rb"<[^>]+>")
_WS_BYTES_RE = re.compile(rb"\s+")
_WS_RE = re.compile(r"\s+")
_CARD_SPLIT_RE = re.compile(rb'<div class="bg-white shadow-sm rounded-3 mb-4">')
_MEDIA_LINK_RE = re.compile(rb"href=['\"](?P<href>/d/(?P<id>\d+))['\"]", re.I)
_SUB_LINK_RE = re.compile(
    rb"<a\b(?P<attrs>[^>]*href=['\"](?P<href>/a/(?P<id>[A-Za-z0-9]+))['\"][^>]*)>"
    rb"(?P<body>.*?)</a>",
    re.I | re.S,
)
_LANG_LABEL_RE = re.compile(rb'<span class="p-1 fw-bold">(?P<label>.*?)</span>', re.I | re.S)
_FORMAT_RE = re.compile(rb'<span class="p-1 text-secondary">(?P<format>.*?)</span>', re.I | re.S)
_DOWNLOAD_COUNT_RE = re.compile(
    rb'bi bi-download.*?</svg>\s*<span class="align-text-top me-3">(?P<count>\d+)</span>',
    re.I | re.S,
)
_RELEASE_RE = re.compile(rb'<div class="f16 fw-bold mb-2">(?P<release>.*?)</div>', re.I | re.S)
_DOWN_LINK_RE = re.compile(
    rb'<a class="btn btn-danger down"\s+sid="(?P<sid>[A-Za-z0-9]+)"\s+href="(?P<href>/down/[A-Za-z0-9]+)"',
    re.I,
)
_DOWN_BUTTON_RE = re.compile(rb'<button class="btn btn-danger down"\s+sid="(?P<sid>[A-Za-z0-9]+)"', re.I)
_FILE_RE = re.compile(rb'data-filename="(?P<filename>[^"]+)"', re.I)
_TITLE_EN_RE = re.compile(rb"<b>Title</b>\s*[:\xef\xbc\x9a]\s*(?P<title>.*?)<br>", re.I | re.S)
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_CAPTCHA_PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*)>", re.I | re.S)
_CAPTCHA_D_RE = re.compile(r'\bd="(?P<d>[^"]+)"')
_CAPTCHA_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_CAPTCHA_TOKEN_RE = re.compile(r"[MmLlQqCcZz]|-?\d+(?:\.\d+)?")


def _decode(data):
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def _strip_tags(data):
    stripped = _TAG_RE.sub(b"", data or b"")
    stripped = _WS_BYTES_RE.sub(b" ", stripped).strip()
    return html.unescape(_decode(stripped))


def _clean_text(value):
    return _WS_RE.sub(" ", html.unescape(_decode(value))).strip()


def _absolute_url(path):
    if not path:
        return None
    value = _decode(path)
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urllib.parse.urljoin(BASE_URL, value)


_LABEL_TO_ALPHA3 = {
    "\u7b80\u4f53": "zho",
    "\u7e41\u4f53": "zho",
    "\u82f1\u8bed": "eng",
    "\u6cd5\u8bed": "fra",
    "\u897f\u73ed\u7259\u8bed": "spa",
    "\u65e5\u8bed": "jpn",
    "\u97e9\u8bed": "kor",
    "\u5fb7\u8bed": "deu",
    "\u963f\u62c9\u4f2f\u8bed": "ara",
    "\u8461\u8404\u7259\u8bed": "por",
    "\u610f\u5927\u5229\u8bed": "ita",
    "\u8377\u5170\u8bed": "nld",
    "\u4fc4\u8bed": "rus",
    "\u571f\u8033\u5176\u8bed": "tur",
    "\u6ce2\u5170\u8bed": "pol",
    "\u745e\u5178\u8bed": "swe",
}
_CHINESE_BILINGUAL_LABELS = {
    "\u53cc\u8bed",
    "\u4e2d\u82f1",
    "\u4e2d\u82f1\u53cc\u8bed",
    "\u7b80\u82f1",
    "\u7e41\u82f1",
}
_ALPHA3_TO_ALPHA2 = {
    "zho": "zh",
    "eng": "en",
    "fra": "fr",
    "spa": "es",
    "jpn": "ja",
    "kor": "ko",
    "deu": "de",
    "ara": "ar",
    "por": "pt",
    "ita": "it",
    "nld": "nl",
    "rus": "ru",
    "tur": "tr",
    "pol": "pl",
    "swe": "sv",
}
_ALPHA2_TO_ALPHA3 = {value: key for key, value in _ALPHA3_TO_ALPHA2.items()}


def _languages_from_block(block):
    labels = [_strip_tags(match.group("label")) for match in _LANG_LABEL_RE.finditer(block or b"")]
    if any(label in _CHINESE_BILINGUAL_LABELS for label in labels):
        return ["zho"]
    result = []
    for label in labels:
        alpha3 = _LABEL_TO_ALPHA3.get(label)
        if alpha3 and alpha3 not in result:
            result.append(alpha3)
    return result


def _format_from_block(block):
    match = _FORMAT_RE.search(block or b"")
    if not match:
        return "srt"
    value = _strip_tags(match.group("format")).lower()
    return value if value in {"srt", "ass", "ssa", "vtt"} else "srt"


def _download_count(block):
    match = _DOWNLOAD_COUNT_RE.search(block or b"")
    return int(match.group("count")) if match else 0


def parse_search_results(html_bytes):
    if not html_bytes:
        return []
    rows = []
    seen = set()
    for block in _CARD_SPLIT_RE.split(html_bytes)[1:]:
        media_match = _MEDIA_LINK_RE.search(block)
        sub_links = list(_SUB_LINK_RE.finditer(block))
        if not media_match or len(sub_links) < 2:
            continue
        title_link = sub_links[0]
        release_link = sub_links[1]
        subtitle_id = _decode(release_link.group("id"))
        if subtitle_id in seen:
            continue
        seen.add(subtitle_id)
        release_info = _strip_tags(release_link.group("body"))
        rows.append(
            {
                "subtitle_id": subtitle_id,
                "media_id": _decode(media_match.group("id")),
                "media_title": _strip_tags(title_link.group("body")),
                "release_info": release_info,
                "languages": _languages_from_block(block),
                "format": _format_from_block(block),
                "download_count": _download_count(block),
                "detail_url": _absolute_url(release_link.group("href")),
            }
        )
    return rows


def parse_detail_page(html_bytes, detail_url):
    if not html_bytes:
        return {}
    down_match = _DOWN_LINK_RE.search(html_bytes)
    button_match = _DOWN_BUTTON_RE.search(html_bytes)
    sid = None
    href = None
    if down_match:
        sid = _decode(down_match.group("sid"))
        href = _decode(down_match.group("href"))
    elif button_match:
        sid = _decode(button_match.group("sid"))
        href = f"/down/{sid}"
    release_match = _RELEASE_RE.search(html_bytes)
    title_match = _TITLE_EN_RE.search(html_bytes)
    files = [_decode(match.group("filename")) for match in _FILE_RE.finditer(html_bytes)]
    return {
        "subtitle_id": sid,
        "media_title": _strip_tags(title_match.group("title")) if title_match else "",
        "release_info": _strip_tags(release_match.group("release")) if release_match else "",
        "languages": _languages_from_block(html_bytes),
        "format": _format_from_block(html_bytes),
        "download_count": _download_count(html_bytes),
        "files": files,
        "detail_url": detail_url,
        "download_url": _absolute_url(href),
    }


def parse_download_response(body):
    data = _parse_download_response_data(body)
    if not data.get("success"):
        raise ValueError(data.get("msg") or "subhd download API failed")
    if data.get("pass") is False:
        raise ValueError("subhd captcha required")
    url = data.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("subhd download API returned no file URL")
    return url


def _parse_download_response_data(body):
    try:
        return json.loads(_decode(body))
    except json.JSONDecodeError as exc:
        raise ValueError("subhd download API returned invalid JSON") from exc


def _captcha_svg_from_response(body):
    data = _parse_download_response_data(body)
    if data.get("pass") is not False:
        return None
    msg = data.get("msg")
    if isinstance(msg, str) and msg.lstrip().startswith("<svg"):
        return msg
    return None


def _extract_captcha_paths(svg_text):
    paths = []
    for match in _CAPTCHA_PATH_RE.finditer(svg_text or ""):
        tag = match.group(0)
        if 'fill="none"' in tag or "fill='none'" in tag:
            continue
        path_match = _CAPTCHA_D_RE.search(tag)
        if not path_match:
            continue
        path = path_match.group("d")
        numbers = [float(value) for value in _CAPTCHA_NUMBER_RE.findall(path)]
        xs = numbers[0::2]
        if xs:
            paths.append((min(xs), path))
    return [path for _, path in sorted(paths)]


def _captcha_path_contours(path):
    tokens = _CAPTCHA_TOKEN_RE.findall(path)
    index = 0
    command = None
    current = (0.0, 0.0)
    start = None
    contours = []
    points = []

    def is_command(token):
        return len(token) == 1 and token.isalpha()

    def number():
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def close_current_contour():
        nonlocal points, start
        if start and (not points or points[-1] != start):
            points.append(start)
        if points:
            contours.append(points)
            points = []
        start = None

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if command in "Mm":
            x, y = number(), number()
            current = (x, y)
            start = current
            if points:
                contours.append(points)
                points = []
            points.append(current)
            command = "L" if command == "M" else "l"
        elif command in "Ll":
            x, y = number(), number()
            if command == "l":
                x += current[0]
                y += current[1]
            current = (x, y)
            points.append(current)
        elif command in "Qq":
            x1, y1, x, y = number(), number(), number(), number()
            if command == "q":
                x1 += current[0]
                y1 += current[1]
                x += current[0]
                y += current[1]
            x0, y0 = current
            for step in range(1, 13):
                t = step / 12
                mt = 1 - t
                points.append(
                    (
                        mt * mt * x0 + 2 * mt * t * x1 + t * t * x,
                        mt * mt * y0 + 2 * mt * t * y1 + t * t * y,
                    )
                )
            current = (x, y)
        elif command in "Cc":
            x1, y1, x2, y2, x, y = number(), number(), number(), number(), number(), number()
            if command == "c":
                x1 += current[0]
                y1 += current[1]
                x2 += current[0]
                y2 += current[1]
                x += current[0]
                y += current[1]
            x0, y0 = current
            for step in range(1, 17):
                t = step / 16
                mt = 1 - t
                points.append(
                    (
                        mt**3 * x0 + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t**3 * x,
                        mt**3 * y0 + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t**3 * y,
                    )
                )
            current = (x, y)
        elif command in "Zz":
            close_current_contour()
        else:
            raise ValueError("subhd captcha contains unsupported SVG path command")
    if points:
        contours.append(points)
    return contours


def _rasterize_captcha_path(path, size=32, pad=2):
    contours = _captcha_path_contours(path)
    all_points = [point for contour in contours for point in contour]
    if not all_points:
        raise ValueError("subhd captcha contained an empty glyph")
    min_x = min(x for x, _ in all_points)
    max_x = max(x for x, _ in all_points)
    min_y = min(y for _, y in all_points)
    max_y = max(y for _, y in all_points)
    scale = (size - 2 * pad) / max(max_x - min_x, max_y - min_y)
    offset_x = (size - (max_x - min_x) * scale) / 2 - min_x * scale
    offset_y = (size - (max_y - min_y) * scale) / 2 - min_y * scale
    scaled_contours = [
        [(x * scale + offset_x, y * scale + offset_y) for x, y in contour]
        for contour in contours
    ]
    rows = []
    for pixel_y in range(size):
        y = pixel_y + 0.5
        row = 0
        for pixel_x in range(size):
            x = pixel_x + 0.5
            winding = 0
            for contour in scaled_contours:
                for (x1, y1), (x2, y2) in zip(contour, contour[1:]):
                    if (y1 <= y < y2) or (y2 <= y < y1):
                        intersection_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1) if y2 != y1 else x1
                        if x < intersection_x:
                            winding += 1 if y1 < y2 else -1
            row = (row << 1) | (1 if winding else 0)
        rows.append(row)
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _captcha_templates():
    templates = []
    for line in CAPTCHA_TEMPLATE_ROWS.splitlines():
        parts = line.split()
        if len(parts) != 33:
            raise ValueError("subhd captcha template row is invalid")
        templates.append((parts[0], tuple(int(row, 16) for row in parts[1:])))
    return tuple(templates)


def _captcha_bitmap_distance(left, right):
    return sum((left_row ^ right_row).bit_count() for left_row, right_row in zip(left, right))


def solve_subhd_captcha(svg_text):
    paths = _extract_captcha_paths(svg_text)
    if len(paths) != 4:
        raise ValueError("subhd captcha solver expected 4 glyphs")
    solved = []
    templates = _captcha_templates()
    for path in paths:
        bitmap = _rasterize_captcha_path(path)
        character, _ = min(
            templates,
            key=lambda item: _captcha_bitmap_distance(bitmap, item[1]),
        )
        solved.append(character)
    return "".join(solved)


def _normalize(text):
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", _coerce_text(text) or "")
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _tokens(text):
    return [token for token in _normalize(text).split(" ") if token]


def _episode_tag_in(text, season, episode):
    normalized = _normalize(text)
    return re.search(rf"\bs0*{int(season)}e0*{int(episode)}\b", normalized) is not None


def derive_matches(video, candidate_title):
    if not video:
        return []
    candidate_tokens = set(_tokens(candidate_title))
    matches = []
    kind = video.get("kind")
    if kind == "movie":
        title_tokens = _tokens(video.get("title"))
        if title_tokens and all(token in candidate_tokens for token in title_tokens):
            matches.append("title")
        year = video.get("year")
        if year and str(year) in candidate_tokens:
            matches.append("year")
    elif kind == "episode":
        series_tokens = _tokens(video.get("series"))
        if series_tokens and all(token in candidate_tokens for token in series_tokens):
            matches.append("series")
        try:
            season = int(video.get("season"))
            episode = int(video.get("episode"))
        except (TypeError, ValueError):
            season = episode = None
        if season is not None and f"s{season:02d}" in _normalize(candidate_title):
            matches.append("season")
        if season is not None and episode is not None and _episode_tag_in(candidate_title, season, episode):
            matches.append("episode")
    release_tokens = {token for token in re.split(r"[^A-Za-z0-9]+", candidate_title.lower()) if token}
    for key in ("source", "resolution", "video_codec", "audio_codec", "release_group"):
        value = _coerce_text(video.get(key))
        parts = [part for part in re.split(r"[^A-Za-z0-9]+", str(value or "").lower()) if part]
        if parts and all(part in release_tokens for part in parts):
            matches.append(key)
    return matches


def compute_score(video, candidate_title):
    matches = derive_matches(video, candidate_title)
    if (video or {}).get("kind") == "movie":
        if "title" in matches and "year" in matches:
            return 100
        if "title" in matches:
            return 90
        return 60
    if (video or {}).get("kind") == "episode":
        if "series" in matches and "episode" in matches:
            return 95
        if "series" in matches:
            return 85
        return 60
    return 60


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    if alpha3:
        return alpha3
    alpha2 = (language.get("alpha2") or "").lower()
    return _ALPHA2_TO_ALPHA3.get(alpha2)


def _alpha2_for_alpha3(alpha3):
    return _ALPHA3_TO_ALPHA2.get(alpha3)


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


class SubHDProvider:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, headers=headers)
        with self._opener.open(request, timeout=timeout) as response:
            return response.read()

    def _http_post_json(self, url, payload, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if referer:
            headers["Referer"] = referer
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with self._opener.open(request, timeout=timeout) as response:
            return response.read()

    def _solve_captcha(self, svg_text):
        return solve_subhd_captcha(svg_text)

    def search(self, video, languages, config):
        config = dict(config or {})
        requested = {_alpha3_for_language(lang) for lang in languages or []}
        requested.discard(None)
        if not requested:
            return []
        results = []
        seen = set()
        for query in build_queries(video):
            url = f"{BASE_URL}/search/{urllib.parse.quote(query, safe='')}"
            _sleep(config)
            rows = parse_search_results(self._http_get(url))
            for row in rows[:MAX_CANDIDATES_PER_QUERY]:
                if row["languages"] and not any(lang in requested for lang in row["languages"]):
                    continue
                _sleep(config)
                try:
                    detail = parse_detail_page(
                        self._http_get(row["detail_url"], referer=url),
                        row["detail_url"],
                    )
                except Exception:
                    continue
                merged = dict(row)
                merged.update({key: value for key, value in detail.items() if value})
                usable_languages = [lang for lang in merged.get("languages", []) if lang in requested]
                if not usable_languages:
                    continue
                for alpha3 in usable_languages:
                    key = (merged["subtitle_id"], alpha3)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(self._result(video, merged, alpha3))
            if results:
                break
        return results

    def _result(self, video, entry, alpha3):
        alpha2 = _alpha2_for_alpha3(alpha3)
        candidate_title = f"{entry.get('media_title', '')} {entry.get('release_info', '')}"
        score = compute_score(video, candidate_title)
        subtitle_id = entry["subtitle_id"]
        fmt = entry.get("format") or "srt"
        return {
            "provider": PROVIDER_ID,
            "id": f"subhd-{subtitle_id}-{alpha3}",
            "language": {
                "alpha3": alpha3,
                "alpha2": alpha2,
                "hi": False,
                "forced": False,
            },
            "release_info": entry.get("release_info") or entry.get("media_title"),
            "filename": f"subhd.{subtitle_id}.{alpha2}.{fmt}",
            "matches": derive_matches(video, candidate_title),
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": entry["detail_url"],
            "display": {
                "source": "subhd",
                "title": entry.get("media_title"),
                "release": entry.get("release_info"),
                "detail_url": entry["detail_url"],
                "downloads": entry.get("download_count", 0),
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": subtitle_id,
                "detail_url": entry["detail_url"],
                "download_url": entry.get("download_url") or f"{BASE_URL}/down/{subtitle_id}",
                "language": alpha3,
                "format": fmt,
                "release_info": entry.get("release_info"),
                "season": (video or {}).get("season"),
                "episode": (video or {}).get("episode"),
            },
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        subtitle_id = payload.get("subtitle_id")
        detail_url = payload.get("detail_url")
        download_url = payload.get("download_url")
        if not subtitle_id or not detail_url or not download_url:
            raise ValueError("subhd download requires subtitle_id, detail_url, and download_url")
        self._http_get(detail_url)
        self._http_get(download_url, referer=detail_url)
        final_url = None
        captcha = ""
        for attempt in range(MAX_CAPTCHA_ATTEMPTS):
            api_body = self._http_post_json(
                API_DOWN_URL,
                {"sid": subtitle_id, "cap": captcha},
                referer=download_url,
            )
            try:
                final_url = parse_download_response(api_body)
                break
            except ValueError:
                captcha_svg = _captcha_svg_from_response(api_body)
                if not captcha_svg or attempt == MAX_CAPTCHA_ATTEMPTS - 1:
                    raise
                captcha = self._solve_captcha(captcha_svg)
                if not captcha:
                    raise ValueError("subhd captcha solver returned no answer")
        if not final_url:
            raise ValueError("subhd download API returned no file URL")
        body = self._http_get(final_url, referer=download_url)
        if _is_archive_body(body):
            # Host-side extraction (Provider Hub v1.1+): hand the raw archive bytes back
            # to the host, which extracts the member and detects encoding. subhd serves
            # zip archives, so list it cheaply with stdlib zipfile to keep our member
            # selection; for the rare rar/7z body let the host pick by episode.
            result = {
                "archive_b64": _base64.b64encode(body).decode("ascii"),
                "archive_sha256": _hashlib.sha256(body).hexdigest(),
            }
            if zipfile.is_zipfile(io.BytesIO(body)):
                result["member"] = _select_archive_member(body)
            else:
                result["episode"] = payload.get("episode")
            return result
        fmt = _format_from_url(final_url, payload.get("format"))
        return _content_payload(body, fmt)


def _format_from_url(url, fallback=None):
    suffix = urllib.parse.urlparse(url or "").path.rsplit(".", 1)[-1].lower()
    if suffix in {"srt", "ass", "ssa", "vtt"}:
        return suffix
    return (fallback or "srt").lower()


def _is_archive_body(body):
    if not body:
        return False
    return (
        zipfile.is_zipfile(io.BytesIO(body))
        or body.startswith(b"Rar!")
        or body.startswith(b"7z\xbc\xaf\x27\x1c")
    )


def _select_archive_member(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(SUBTITLE_EXTENSIONS)]
    if not names:
        raise ValueError("subhd archive contained no subtitle files")
    names.sort(key=lambda name: (not name.lower().endswith(".srt"), len(name), name.lower()))
    return names[0]


def _content_payload(body, fmt):
    if not body:
        raise ValueError("subhd downloaded empty subtitle")
    if _is_html_body(body):
        raise ValueError("subhd returned an HTML/error page instead of a subtitle")
    return {
        "content_b64": _base64.b64encode(body).decode("ascii"),
        "content_sha256": _hashlib.sha256(body).hexdigest(),
        "content_type": _content_type(fmt),
        "format": fmt,
        "empty": False,
    }


def _is_html_body(body):
    head = body[:1024].lstrip().lower()
    return (
        head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or head.startswith(b"<?xml")
        or b"<body" in head
        or b"<head" in head
    )


def _content_type(fmt):
    if fmt == "ass":
        return "text/x-ssa"
    if fmt == "ssa":
        return "text/x-ssa"
    if fmt == "vtt":
        return "text/vtt"
    return "application/x-subrip"
