"""Nekur provider for the Bazarr+ Provider Hub catalog."""

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

PROVIDER_ID = "nekur"
BASE_URL = "https://subtitri.nekur.net"
SEARCH_URL = f"{BASE_URL}/modules/Subtitles.php"
HTTP_TIMEOUT_SECONDS = 10
SUPPORTED_LANGUAGES = {"lav": "lv"}
LANGUAGE_ALIASES = {"lv": "lav", "lva": "lav", "lva-lv": "lav"}
SUBTITLE_EXTENSIONS = (".srt", ".sub", ".ssa", ".ass", ".vtt")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(?P<body>.*?)</t[dh]>", re.I | re.S)
_ANCHOR_RE = re.compile(r"<a\b[^>]*href=['\"](?P<href>[^'\"]+)['\"][^>]*>(?P<body>.*?)</a>", re.I | re.S)
_IMDB_RE = re.compile(r"imdb\.com/title/(?P<imdb>tt\d+)/?", re.I)
_YEAR_RE = re.compile(r"\((?P<year>\d{4})\)")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


def parse_search_results(body):
    text = _decode_html(body)
    rows = []
    for row_match in _ROW_RE.finditer(text):
        row_html = row_match.group("body")
        if "filmu-subtitri/download/" not in row_html:
            continue
        cells = [match.group("body") for match in _CELL_RE.finditer(row_html)]
        if len(cells) < 6:
            continue
        title_anchor = _ANCHOR_RE.search(cells[0])
        if not title_anchor:
            continue
        href = html.unescape(title_anchor.group("href"))
        title_text = _strip_tags(title_anchor.group("body"))
        year = _year_from_text(title_text)
        title = _YEAR_RE.sub("", title_text).strip()
        imdb = _imdb_from_cell(cells[3])
        if not title or not imdb:
            continue
        rows.append(
            {
                "title": title,
                "year": year,
                "download_url": _absolute_url(href),
                "subtitle_id": _subtitle_id_from_url(href),
                "imdb_id": imdb,
                "fps": _strip_tags(cells[1]),
                "notes": _strip_tags(cells[-1]),
            }
        )
    return rows


def derive_matches(video, item, searched_title=None):
    matches = []
    title_candidates = _search_titles(video or {})
    searched_title = str(searched_title or "").strip()
    if searched_title and searched_title not in title_candidates:
        title_candidates.append(searched_title)
    if any(_title_matches(title, item.get("title")) for title in title_candidates):
        matches.append("title")
    try:
        if (video or {}).get("year") and int(video.get("year")) == int(item.get("year")):
            matches.append("year")
    except (TypeError, ValueError):
        pass
    if _normalize_imdb((video or {}).get("imdb_id")) == _normalize_imdb(item.get("imdb_id")):
        matches.append("imdb_id")
    source = _normalize_release((video or {}).get("source"))
    notes = _normalize_release(item.get("notes"))
    if source and source in notes:
        matches.append("source")
    release_group = _normalize_release((video or {}).get("release_group"))
    if release_group and release_group in notes:
        matches.append("release_group")
    return matches


class NekurProvider:
    def _http_post_search(self, title, timeout=HTTP_TIMEOUT_SECONDS):
        data = urllib.parse.urlencode({"ajax": "1", "sSearch": title}).encode("utf-8")
        request = urllib.request.Request(
            SEARCH_URL,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": f"{BASE_URL}/",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "lv-LV,lv;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            body = error.read()
            if error.code >= 500 and body:
                return body
            raise

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": f"{BASE_URL}/",
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), _headers_to_dict(response.headers)

    def search(self, video, languages, config):
        if (video or {}).get("kind") != "movie":
            return []
        if not _requests_latvian(languages):
            return []
        titles = _search_titles(video)
        if not titles:
            return []

        config = dict(config or {})
        results = []
        seen = set()
        for title in titles:
            _sleep(config)
            rows = parse_search_results(self._http_post_search(title))
            for row in rows:
                matches = derive_matches(video, row, searched_title=title)
                if not _has_required_match(video, matches):
                    continue
                key = row["download_url"]
                if key in seen:
                    continue
                seen.add(key)
                results.append(self._result(row, matches))
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _result(self, item, matches):
        score = 45
        score += 30 if "imdb_id" in matches else 0
        score += 15 if "title" in matches else 0
        score += 10 if "year" in matches else 0
        score += 5 if "source" in matches else 0
        release_info = item.get("notes") or f"{item.get('title')} {item.get('year') or ''}".strip()
        filename = f"nekur.{_slug(item.get('title'))}.{item.get('year') or 'unknown'}.lv.zip"
        return {
            "provider": PROVIDER_ID,
            "id": f"nekur-{item['subtitle_id']}",
            "language": {
                "alpha3": "lav",
                "alpha2": "lv",
                "hi": False,
                "forced": False,
            },
            "release_info": release_info,
            "filename": filename,
            "matches": matches,
            "score": min(score, 100),
            "score_without_hash": min(score, 100),
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": item["download_url"],
            "display": {
                "source": "subtitri.nekur.net",
                "title": item.get("title"),
                "release": release_info,
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "download_url": item["download_url"],
                "subtitle_id": item["subtitle_id"],
                "filename": filename,
                "title": item.get("title"),
                "year": item.get("year"),
                "season": item.get("season"),
                "episode": item.get("episode"),
                "imdb_id": item.get("imdb_id"),
                "fps": item.get("fps"),
                "notes": item.get("notes"),
            },
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        url = payload.get("download_url")
        if not url:
            raise ValueError("nekur download requires download_url")
        body, headers = self._http_get(url)
        # The synthetic ".zip" filename only describes archive responses. When the
        # endpoint serves a direct subtitle, prefer the real Content-Disposition
        # name so its true extension survives into the direct-content path.
        filename = _filename_from_headers(headers) or payload.get("filename", "")
        return extract_download(body, filename, payload)


def extract_download(body, filename="", payload=None):
    payload = payload or {}
    # Reject broken responses up front: the endpoint can answer with an empty
    # stream or an HTML/error page that would otherwise look like a download.
    if not body:
        raise ValueError("nekur download returned an empty response")
    if _looks_like_html(body):
        raise ValueError("nekur download did not return a supported subtitle file")
    if _is_archive_body(body):
        # A multi-part subtitle (CD1/CD2 ...) has to be concatenated, which the
        # single-member host contract cannot do: an episode/member pick would return
        # only one disc. When we can list a zip and it holds a multipart set, join those
        # members here and return direct content so the user gets the whole subtitle.
        multipart = _multipart_content(body, payload)
        if multipart is not None:
            return multipart
        # Otherwise host-side extraction (Provider Hub v1.1+): hand the raw archive bytes
        # back to the host, which lists it, picks the member by episode, and detects
        # encoding via Subtitle.normalize(). RAR is not stdlib-listable (and bundling
        # rarfile/py7zz is banned), so a multipart rar also falls back to the host here.
        return {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
            "episode": payload.get("episode"),
        }
    # Direct (non-archive) subtitle: trust the real filename extension, then fall
    # back to sniffing the body so a valid .srt/.sub is not rejected just because
    # the synthetic ".zip" filename carried no usable extension.
    subtitle_format = _subtitle_extension(filename or "") or _format_from_content(body)
    if not subtitle_format:
        raise ValueError("nekur download did not return a supported subtitle file")
    return _content_payload(body, subtitle_format)


def _is_archive_body(body):
    return _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _multipart_content(body, payload):
    # Concatenate a CD1/CD2-style multipart subtitle from a zip into one content payload.
    # Listing only (no host-banned rar/7z libs). Returns None when the archive is not a
    # listable zip, holds no multipart set, or a single file scores better than the
    # multipart group, so the caller falls back to the host archive path.
    if _is_rar_archive(body) or not zipfile.is_zipfile(io.BytesIO(body)):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [
            name
            for name in archive.namelist()
            if _subtitle_extension(name) and not _is_sidecar(name)
        ]
        multipart = _multipart_subset(names, payload)
        if not multipart:
            return None
        # Only prefer the multipart set when it scores at least as well as the best single
        # file; otherwise a stray CD1/CD2 pair would shadow a better-matching single sub,
        # and the host's episode pick over the whole archive is the safer choice.
        best_single_score = max(
            (_subtitle_file_score(name, payload) for name in names), default=0
        )
        if _group_score(multipart, payload) < best_single_score:
            return None
        content = b"\n\n".join(archive.read(name) for name in multipart)
    return _content_payload(content, _subtitle_extension(multipart[0]) or "srt")


def _is_sidecar(name):
    parts = name.replace("\\", "/").split("/")
    if any(part == "__MACOSX" for part in parts):
        return True
    return os.path.basename(name).startswith("._")


def _group_score(names, payload):
    return max(_subtitle_file_score(name, payload) for name in names)


def _subtitle_file_score(name, payload):
    title_tokens = _tokens((payload or {}).get("title"))
    year = str((payload or {}).get("year") or "")
    note_tokens = _tokens((payload or {}).get("notes"))
    wants_forced = bool((payload or {}).get("forced"))
    normalized = _normalize(os.path.basename(name))
    tokens = set(normalized.split())
    value = 0
    if title_tokens and all(token in tokens for token in title_tokens):
        value += 80
    if year and year in normalized:
        value += 50
    for token in note_tokens:
        if token in tokens:
            value += 5
    if not wants_forced and "forced" in tokens:
        value -= 25
    return value


def _multipart_subset(names, payload):
    groups = {}
    for name in names:
        if _part_index(name) <= 0:
            continue
        groups.setdefault((_multipart_key(name), _subtitle_extension(name)), []).append(name)
    valid_groups = []
    for group in groups.values():
        part_numbers = [_part_index(name) for name in group]
        if len(group) > 1 and len(set(part_numbers)) == len(part_numbers):
            valid_groups.append(group)
    if not valid_groups:
        return []
    best_group = max(
        valid_groups,
        key=lambda group: (
            _group_score(group, payload),
            len(group),
            -min(_part_index(name) for name in group),
        ),
    )
    return sorted(best_group, key=lambda name: (_part_index(name), name.lower()))


def _part_index(name):
    normalized = _normalize(os.path.basename(name))
    match = re.search(r"\b(?:cd|part|disc|disk)\s*0*(\d+)\b", normalized)
    return int(match.group(1)) if match else 0


def _multipart_key(name):
    stem = os.path.splitext(os.path.basename(name))[0]
    normalized = _normalize(stem)
    return re.sub(r"\b(?:cd|part|disc|disk)\s*0*\d+\b", "", normalized).strip()


def _requests_latvian(languages):
    for language in languages or []:
        if _alpha3_for_language(language) == "lav":
            return True
    return False


def _search_titles(video):
    titles = []
    for value in [video.get("title")] + list(video.get("alternative_titles") or []):
        value = str(value or "").strip()
        if value and value not in titles:
            titles.append(value)
    return titles


def _has_required_match(video, matches):
    if "imdb_id" in matches:
        return True
    if "title" in matches and ("year" in matches or not (video or {}).get("year")):
        return True
    return False


def _title_matches(wanted, candidate):
    wanted_tokens = _tokens(wanted)
    candidate_tokens = set(_tokens(candidate))
    return bool(wanted_tokens) and all(token in candidate_tokens for token in wanted_tokens)


def _year_from_text(text):
    match = _YEAR_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group("year"))
    except (TypeError, ValueError):
        return None


def _imdb_from_cell(cell):
    match = _IMDB_RE.search(cell or "")
    return match.group("imdb") if match else ""


def _subtitle_id_from_url(url):
    path = urllib.parse.urlparse(url or "").path
    return os.path.basename(path.rstrip("/"))


def _absolute_url(value):
    return urllib.parse.urljoin(BASE_URL + "/", value)


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


def _headers_to_dict(headers):
    return {str(key).lower(): str(value) for key, value in dict(headers or {}).items()}


def _filename_from_headers(headers):
    disposition = (headers or {}).get("content-disposition", "")
    match = re.search(r'filename\*?=(?:[^\'";]+\'\')?"?([^";]+)"?', disposition)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1)).strip()


def _format_from_content(body):
    sample = (body or b"").lstrip()[:512]
    if sample.startswith(b"\xef\xbb\xbf"):
        sample = sample[3:].lstrip()
    if sample.upper().startswith(b"WEBVTT"):
        return "vtt"
    lowered = sample.lower()
    if b"[script info]" in lowered or b"[v4+ styles]" in lowered or b"[v4 styles]" in lowered:
        return "ass"
    # SubRip cue: a numeric index line followed by a "hh:mm:ss,mmm --> ..." timecode.
    if re.search(rb"(?m)^\s*\d+\s*\r?\n\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", sample):
        return "srt"
    # MicroDVD .sub frames such as "{0}{25}text".
    if re.match(rb"\s*\{\d+\}\{\d+\}", sample):
        return "sub"
    return None


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a
    # worker guess (especially a legacy codepage that never fails to decode) only
    # reintroduces mojibake. Leave encoding unset and let the host normalize.
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


def _looks_like_html(body):
    sample = (body or b"").lstrip()[:512].lower()
    return sample.startswith((b"<!doctype html", b"<html")) or b"<title" in sample


def _alpha3_for_language(language):
    if isinstance(language, dict):
        alpha3 = (language.get("alpha3") or "").lower()
        if alpha3 in LANGUAGE_ALIASES:
            return LANGUAGE_ALIASES[alpha3]
        if alpha3:
            return alpha3
        alpha2 = (language.get("alpha2") or "").lower()
        return LANGUAGE_ALIASES.get(alpha2, alpha2)
    value = str(language or "").lower()
    return LANGUAGE_ALIASES.get(value, value)


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(int(delay_ms), 5000) / 1000.0)


def _strip_tags(value):
    stripped = _TAG_RE.sub("", value or "")
    return _WS_RE.sub(" ", html.unescape(stripped)).strip()


def _decode_html(body):
    if isinstance(body, str):
        return body
    raw = body or b""
    for encoding in ("utf-8", "cp1257", "latin-1"):
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


def _normalize_imdb(value):
    value = str(value or "").strip()
    if not value:
        return ""
    return value if value.startswith("tt") else f"tt{value}"


def _normalize_release(value):
    return _normalize(value).replace(" ", "")
