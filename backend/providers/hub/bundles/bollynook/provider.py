"""BollyNook provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import html
import io
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "bollynook"
BASE_URL = "https://www.bollynook.com"
HTTP_TIMEOUT_SECONDS = 15
MAX_RESULTS = 20
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

LANGUAGES = {
    "arg": {"alpha2": "an", "site_code": "arg", "slug": "aragonese", "name": "Aragonese"},
    "ara": {"alpha2": "ar", "site_code": "ara", "slug": "arabic", "name": "Arabic"},
    "aze": {"alpha2": "az", "site_code": "ale", "slug": "azerbaijani", "name": "Azerbaijani"},
    "bel": {"alpha2": "be", "site_code": "bel", "slug": "belarusian", "name": "Belarusian"},
    "bos": {"alpha2": "bs", "site_code": "bos", "slug": "bosnian", "name": "Bosnian"},
    "bul": {"alpha2": "bg", "site_code": "bgr", "slug": "bulgarian", "name": "Bulgarian"},
    "ces": {"alpha2": "cs", "site_code": "cze", "slug": "czech", "name": "Czech"},
    "dan": {"alpha2": "da", "site_code": "dan", "slug": "danish", "name": "Danish"},
    "deu": {"alpha2": "de", "site_code": "ger", "slug": "german", "name": "German"},
    "ell": {"alpha2": "el", "site_code": "gre", "slug": "greek", "name": "Greek"},
    "eng": {"alpha2": "en", "site_code": "eng", "slug": "english", "name": "English"},
    "fas": {"alpha2": "fa", "site_code": "per", "slug": "persian-farsi", "name": "Persian Farsi"},
    "fin": {"alpha2": "fi", "site_code": "fin", "slug": "finnish", "name": "Finnish"},
    "fra": {"alpha2": "fr", "site_code": "fra", "slug": "french", "name": "French"},
    "gle": {"alpha2": "ga", "site_code": "gle", "slug": "irish", "name": "Irish"},
    "heb": {"alpha2": "he", "site_code": "heb", "slug": "hebrew", "name": "Hebrew"},
    "hin": {"alpha2": "hi", "site_code": "hin", "slug": "hindi", "name": "Hindi"},
    "hrv": {"alpha2": "hr", "site_code": "cro", "slug": "croatian", "name": "Croatian"},
    "hun": {"alpha2": "hu", "site_code": "hun", "slug": "hungarian", "name": "Hungarian"},
    "hye": {"alpha2": "hy", "site_code": "arm", "slug": "armenian", "name": "Armenian"},
    "ind": {"alpha2": "id", "site_code": "ind", "slug": "indonesian", "name": "Indonesian"},
    "ita": {"alpha2": "it", "site_code": "ita", "slug": "italian", "name": "Italian"},
    "jpn": {"alpha2": "ja", "site_code": "jpn", "slug": "japanese", "name": "Japanese"},
    "kor": {"alpha2": "ko", "site_code": "kor", "slug": "korean", "name": "Korean"},
    "lav": {"alpha2": "lv", "site_code": "lav", "slug": "latvian", "name": "Latvian"},
    "lit": {"alpha2": "lt", "site_code": "lit", "slug": "lithuanian", "name": "Lithuanian"},
    "mkd": {"alpha2": "mk", "site_code": "mac", "slug": "macedonian", "name": "Macedonian"},
    "msa": {"alpha2": "ms", "site_code": "may", "slug": "malay", "name": "Malay"},
    "nld": {"alpha2": "nl", "site_code": "dut", "slug": "dutch", "name": "Dutch"},
    "nor": {"alpha2": "no", "site_code": "nor", "slug": "norwegian", "name": "Norwegian"},
    "pol": {"alpha2": "pl", "site_code": "pol", "slug": "polish", "name": "Polish"},
    "por": {"alpha2": "pt", "site_code": "por", "slug": "portuguese", "name": "Portuguese"},
    "ron": {"alpha2": "ro", "site_code": "rum", "slug": "romanian", "name": "Romanian"},
    "rus": {"alpha2": "ru", "site_code": "rus", "slug": "russian", "name": "Russian"},
    "sin": {"alpha2": "si", "site_code": "sin", "slug": "sinhala", "name": "Sinhala"},
    "slk": {"alpha2": "sk", "site_code": "slo", "slug": "slovak", "name": "Slovak"},
    "slv": {"alpha2": "sl", "site_code": "slv", "slug": "slovenian", "name": "Slovenian"},
    "spa": {"alpha2": "es", "site_code": "spn", "slug": "spanish", "name": "Spanish"},
    "srp": {"alpha2": "sr", "site_code": "srb", "slug": "serbian", "name": "Serbian"},
    "sqi": {"alpha2": "sq", "site_code": "alb", "slug": "albanian", "name": "Albanian"},
    "swe": {"alpha2": "sv", "site_code": "swe", "slug": "swedish", "name": "Swedish"},
    "tha": {"alpha2": "th", "site_code": "tha", "slug": "thai", "name": "Thai"},
    "tur": {"alpha2": "tr", "site_code": "tur", "slug": "turkish", "name": "Turkish"},
    "ukr": {"alpha2": "uk", "site_code": "ukr", "slug": "ukrainian", "name": "Ukrainian"},
    "vie": {"alpha2": "vi", "site_code": "vie", "slug": "vietnamese", "name": "Vietnamese"},
    "zho": {"alpha2": "zh", "site_code": "chi", "slug": "chinese", "name": "Chinese"},
}
_SITE_CODE_TO_ALPHA3 = {value["site_code"]: key for key, value in LANGUAGES.items()}
_SLUG_TO_ALPHA3 = {value["slug"]: key for key, value in LANGUAGES.items()}
_ALPHA2_TO_ALPHA3 = {value["alpha2"]: key for key, value in LANGUAGES.items()}

_RESULT_BLOCK_RE = re.compile(rb"<li\b[^>]*>(?P<body>.*?)</li>", re.I | re.S)
_MOVIE_LINK_RE = re.compile(
    rb"Movie:&nbsp;.*?<a\b[^>]*href=['\"](?P<href>/en/bollywood-movie-subtitles/(?P<id>\d+)/[^'\"]+/)['\"][^>]*>(?P<title>.*?)</a>",
    re.I | re.S,
)
_LANG_CODE_RE = re.compile(rb"/images/zastave/(?P<code>[a-z]+)\.png", re.I)
_PUBLISHED_RE = re.compile(rb"Published:\s*(?P<published>\d{2}\.\d{2}\.\d{4}\.)", re.I)
_DOWNLOAD_RE = re.compile(rb"<a\b[^>]*class=['\"][^'\"]*\bdownloads\b[^'\"]*['\"][^>]*href=['\"](?P<href>[^'\"]+)['\"]", re.I | re.S)
_H1_RE = re.compile(rb"<h1>(?P<title>.*?)</h1>", re.I | re.S)
_YEAR_RE = re.compile(rb"Year:\s*<strong>(?P<year>\d{4})</strong>", re.I)
_CDS_RE = re.compile(rb"Number of CD's:\s*<strong>(?P<cds>\d+)</strong>", re.I)
_UPLOADER_RE = re.compile(rb"Uploader:\s*<a\b[^>]*>\s*<strong>(?P<uploader>.*?)</strong>", re.I | re.S)
_LANG_NAME_RE = re.compile(rb"data-original-title=['\"](?P<name>[^'\"]+)['\"]", re.I)
_TAG_RE = re.compile(rb"<[^>]+>")
_WS_BYTES_RE = re.compile(rb"\s+")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_TITLE_YEAR_RE = re.compile(r"(?:-|/)\s*(\d{4})\b")


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
    rows = []
    seen = set()
    for block_match in _RESULT_BLOCK_RE.finditer(body or b""):
        block = block_match.group("body")
        link_match = _MOVIE_LINK_RE.search(block)
        if not link_match:
            continue
        movie_id = _decode(link_match.group("id"))
        if movie_id in seen:
            continue
        language = _language_from_block(block)
        if not language:
            continue
        title = _strip_tags(link_match.group("title"))
        seen.add(movie_id)
        rows.append(
            {
                "movie_id": movie_id,
                "title": title,
                "year": _year_from_title(title),
                "language": language,
                "url": _absolute_url(_decode(link_match.group("href"))),
                "published": _strip_tags(_PUBLISHED_RE.search(block).group("published")) if _PUBLISHED_RE.search(block) else "",
            }
        )
    return rows


def parse_detail(body, page_url):
    title_match = _H1_RE.search(body or b"")
    download_match = _DOWNLOAD_RE.search(body or b"")
    if not title_match or not download_match:
        raise ValueError("bollynook subtitle detail is missing title or download link")
    lang = _language_from_block(body or b"")
    year_match = _YEAR_RE.search(body or b"")
    cds_match = _CDS_RE.search(body or b"")
    uploader_match = _UPLOADER_RE.search(body or b"")
    return {
        "title": _strip_tags(title_match.group("title")),
        "year": int(year_match.group("year")) if year_match else None,
        "language": lang,
        "cds": int(cds_match.group("cds")) if cds_match else 1,
        "uploader": _strip_tags(uploader_match.group("uploader")) if uploader_match else "",
        "download_url": _absolute_url(_decode(download_match.group("href"))),
        "page_url": page_url,
    }


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


class BollyNookProvider:
    def _http_request(self, url, data=None, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
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
            for alpha3 in requested:
                _sleep(config)
                post_body = urllib.parse.urlencode(
                    {
                        "type": "2",
                        "title": query,
                        "language": LANGUAGES[alpha3]["site_code"],
                        "submit": "Search",
                    }
                ).encode("ascii")
                search_body = self._http_request(f"{BASE_URL}/en/search/", data=post_body)
                for row in _rank_search_results(video, parse_search_results(search_body)):
                    if row["language"] != alpha3:
                        continue
                    key = (row["movie_id"], row["language"])
                    if key in seen:
                        continue
                    _sleep(config)
                    try:
                        detail_body = self._http_request(row["url"], referer=f"{BASE_URL}/en/search/")
                        detail = parse_detail(detail_body, row["url"])
                    except (OSError, ValueError):
                        continue
                    if detail["language"] != alpha3 or not _row_matches_video(video, row, detail):
                        continue
                    seen.add(key)
                    results.append(self._result(video, row, detail))
                    if len(results) >= MAX_RESULTS:
                        return _sort_results(results)
        return _sort_results(results)

    def _result(self, video, row, detail):
        language = LANGUAGES[row["language"]]
        candidate_title = f"{detail['title']} {detail.get('year') or ''}"
        matches = derive_matches(video, candidate_title)
        score = 95 if "year" in matches else 85
        filename = os.path.basename(urllib.parse.urlparse(detail["download_url"]).path) or f"bollynook.{row['movie_id']}.zip"
        return {
            "provider": PROVIDER_ID,
            "id": f"bollynook-{row['movie_id']}-{row['language']}",
            "language": {
                "alpha3": row["language"],
                "alpha2": language["alpha2"],
                "hi": False,
                "forced": False,
            },
            "release_info": candidate_title.strip(),
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": detail["page_url"],
            "display": {
                "source": "bollynook",
                "title": detail["title"],
                "year": detail.get("year"),
                "uploader": detail.get("uploader"),
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "movie_id": row["movie_id"],
                "url": detail["download_url"],
                "page_url": detail["page_url"],
                "filename": filename,
                "language": row["language"],
            },
        }

    def download(self, provider_payload, language, config):
        del config
        payload = dict(provider_payload or {})
        payload.setdefault("language", _alpha3_for_language(language))
        url = payload.get("url")
        if not url:
            raise ValueError("bollynook download requires url")
        body = self._http_request(url, referer=payload.get("page_url"))
        return extract_download(body, payload)


def _is_rar_or_7z(body):
    head = body[:8] if body else b""
    return head.startswith((b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c"))


def extract_download(body, payload=None):
    payload = payload or {}
    # Reject broken responses up front: an empty stream or an HTML/error page would
    # otherwise be handed back as a bogus "subtitle".
    if not body or not body.strip():
        raise ValueError("bollynook empty download")
    if _is_html_body(body):
        raise ValueError("bollynook returned an HTML/error page")
    if zipfile.is_zipfile(io.BytesIO(body)):
        # Host-side extraction (Provider Hub v1.1+): the worker still lists the zip
        # cheaply with stdlib to pick the right-language member, then hands the raw
        # archive bytes and the chosen member name back to the host, which extracts
        # it and detects the encoding via Subtitle.normalize().
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            selected = select_subtitle_file(archive.namelist(), payload)
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "member": selected,
        }
    if _is_rar_or_7z(body):
        # RAR/7z: the stdlib-only worker can't list members, so hand the raw archive
        # to the host (rarfile/py7zr), which extracts it and picks by episode. Without
        # this branch a rar/7z body falls through and is mis-served as raw subtitle text.
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "episode": payload.get("episode"),
        }
    # Direct, non-archive subtitle body.
    return _content_payload(body, _subtitle_extension(payload.get("filename", "")) or "srt")


def select_subtitle_file(names, payload=None):
    candidates = [name for name in names if _subtitle_extension(name)]
    if not candidates:
        raise ValueError("bollynook archive contains no supported subtitle files")
    language_tokens = _language_tokens((payload or {}).get("language"))
    if language_tokens:
        scored = [(_language_score(name, language_tokens), index, name) for index, name in enumerate(candidates)]
        best_score, _index, best_name = max(scored, key=lambda item: (item[0], -item[1]))
        if best_score > 0:
            return best_name
    return candidates[0]


def _rank_search_results(video, rows):
    ranked = []
    wanted_tokens = _tokens((video or {}).get("title"))
    wanted_norm = _normalize((video or {}).get("title"))
    for index, row in enumerate(rows):
        title_without_year = _TITLE_YEAR_RE.sub("", row["title"]).strip()
        row_tokens = set(_tokens(title_without_year))
        score = 0
        if wanted_tokens and all(token in row_tokens for token in wanted_tokens):
            score = 80
        if wanted_norm and _normalize(title_without_year) == wanted_norm:
            score = 110
        try:
            wanted_year = int((video or {}).get("year"))
        except (TypeError, ValueError):
            wanted_year = None
        if wanted_year is not None and row.get("year") == wanted_year:
            score += 10
        if score:
            ranked.append((row, score, index))
    ranked.sort(key=lambda item: (-item[1], item[2]))
    return [row for row, _score, _index in ranked]


def _row_matches_video(video, row, detail):
    wanted_year = _safe_int((video or {}).get("year"))
    candidate_year = _safe_int((detail or {}).get("year"))
    if candidate_year is None:
        candidate_year = _safe_int((row or {}).get("year"))
    if wanted_year is not None and candidate_year is not None and candidate_year != wanted_year:
        return False
    matches = derive_matches(video, f"{detail['title']} {detail.get('year') or row.get('year') or ''}")
    return "title" in matches


def _sort_results(results):
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _language_from_block(block):
    code_match = _LANG_CODE_RE.search(block or b"")
    if code_match:
        alpha3 = _SITE_CODE_TO_ALPHA3.get(_decode(code_match.group("code")).lower())
        if alpha3:
            return alpha3
    name_match = _LANG_NAME_RE.search(block or b"")
    if name_match:
        wanted = _strip_tags(name_match.group("name")).lower()
        for alpha3, meta in LANGUAGES.items():
            if meta["name"].lower() == wanted:
                return alpha3
    slug_match = re.search(rb"/en/language/2/(?P<slug>[^/]+)/", block or b"", re.I)
    if slug_match:
        return _SLUG_TO_ALPHA3.get(_decode(slug_match.group("slug")).lower())
    return None


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    if alpha3:
        return alpha3
    return _ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())


def _absolute_url(path):
    return urllib.parse.urljoin(BASE_URL + "/", path)


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially a legacy codepage that never fails to decode) only reintroduces
    # mojibake. Leave encoding unset and let the host normalize.
    return {
        "content_b64": _base64.b64encode(content).decode("ascii"),
        "content_sha256": _hashlib.sha256(content).hexdigest(),
        "content_type": _content_type(subtitle_format),
        "format": subtitle_format,
        "empty": False,
    }


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


def _content_type(subtitle_format):
    if subtitle_format in {"ass", "ssa"}:
        return "text/x-ssa"
    if subtitle_format == "vtt":
        return "text/vtt"
    return "application/x-subrip"


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _year_from_title(title):
    match = _TITLE_YEAR_RE.search(title or "")
    return int(match.group(1)) if match else None


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _language_tokens(alpha3):
    meta = LANGUAGES.get((alpha3 or "").lower())
    if not meta:
        return set()
    values = {alpha3, meta["alpha2"], meta["site_code"], meta["slug"], meta["name"]}
    tokens = set()
    for value in values:
        tokens.update(_tokens(value))
    return tokens


def _language_score(name, language_tokens):
    filename_tokens = set(_tokens(os.path.basename(name)))
    return len(filename_tokens & language_tokens)


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


def _decode(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")
