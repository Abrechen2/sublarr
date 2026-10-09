"""Subsarr provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

PROVIDER_ID = "subsarr"
HTTP_TIMEOUT_SECONDS = 30
MAX_RESULTS = 100
PER_PAGE = 100
MAX_SEARCH_PAGES = 5
USER_AGENT = "Subliminal/2 Bazarr/1"

LANGUAGE_SLUGS = {
    "abk": {"alpha2": "ab", "slug": "abkhazian"},
    "afr": {"alpha2": "af", "slug": "afrikaans"},
    "amh": {"alpha2": "am", "slug": "amharic"},
    "ara": {"alpha2": "ar", "slug": "arabic"},
    "arg": {"alpha2": "an", "slug": "aragonese"},
    "asm": {"alpha2": "as", "slug": "assamese"},
    "aze": {"alpha2": "az", "slug": "azerbaijani"},
    "bel": {"alpha2": "be", "slug": "belarusian"},
    "ben": {"alpha2": "bn", "slug": "bengali"},
    "bos": {"alpha2": "bs", "slug": "bosnian"},
    "bre": {"alpha2": "br", "slug": "breton"},
    "bul": {"alpha2": "bg", "slug": "bulgarian"},
    "cat": {"alpha2": "ca", "slug": "catalan"},
    "ces": {"alpha2": "cs", "slug": "czech"},
    "cym": {"alpha2": "cy", "slug": "welsh"},
    "dan": {"alpha2": "da", "slug": "danish"},
    "deu": {"alpha2": "de", "slug": "german"},
    "ell": {"alpha2": "el", "slug": "greek"},
    "eng": {"alpha2": "en", "slug": "english"},
    "epo": {"alpha2": "eo", "slug": "esperanto"},
    "est": {"alpha2": "et", "slug": "estonian"},
    "eus": {"alpha2": "eu", "slug": "basque"},
    "fas": {"alpha2": "fa", "slug": "farsi_persian"},
    "fin": {"alpha2": "fi", "slug": "finnish"},
    "fra": {"alpha2": "fr", "slug": "french"},
    "gla": {"alpha2": "gd", "slug": "gaelic"},
    "gle": {"alpha2": "ga", "slug": "irish"},
    "heb": {"alpha2": "he", "slug": "hebrew"},
    "hin": {"alpha2": "hi", "slug": "hindi"},
    "hrv": {"alpha2": "hr", "slug": "croatian"},
    "hun": {"alpha2": "hu", "slug": "hungarian"},
    "hye": {"alpha2": "hy", "slug": "armenian"},
    "ibo": {"alpha2": "ig", "slug": "igbo"},
    "ina": {"alpha2": "ia", "slug": "interlingua"},
    "ind": {"alpha2": "id", "slug": "indonesian"},
    "isl": {"alpha2": "is", "slug": "icelandic"},
    "ita": {"alpha2": "it", "slug": "italian"},
    "jpn": {"alpha2": "ja", "slug": "japanese"},
    "kan": {"alpha2": "kn", "slug": "kannada"},
    "kat": {"alpha2": "ka", "slug": "georgian"},
    "kaz": {"alpha2": "kk", "slug": "kazakh"},
    "khm": {"alpha2": "km", "slug": "cambodian-khmer"},
    "kin": {"alpha2": "rw", "slug": "kinyarwanda"},
    "kor": {"alpha2": "ko", "slug": "korean"},
    "kur": {"alpha2": "ku", "slug": "kurdish"},
    "lav": {"alpha2": "lv", "slug": "latvian"},
    "lit": {"alpha2": "lt", "slug": "lithuanian"},
    "ltz": {"alpha2": "lb", "slug": "luxembourgish"},
    "mal": {"alpha2": "ml", "slug": "malayalam"},
    "mar": {"alpha2": "mr", "slug": "marathi"},
    "mkd": {"alpha2": "mk", "slug": "macedonian"},
    "mon": {"alpha2": "mn", "slug": "mongolian"},
    "msa": {"alpha2": "ms", "slug": "malay"},
    "mya": {"alpha2": "my", "slug": "burmese"},
    "nav": {"alpha2": "nv", "slug": "navajo"},
    "nep": {"alpha2": "ne", "slug": "nepali"},
    "nld": {"alpha2": "nl", "slug": "dutch"},
    "nor": {"alpha2": "no", "slug": "norwegian"},
    "oci": {"alpha2": "oc", "slug": "occitan"},
    "pan": {"alpha2": "pa", "slug": "punjabi"},
    "pol": {"alpha2": "pl", "slug": "polish"},
    "por": {"alpha2": "pt", "slug": "portuguese"},
    "por-BR": {"alpha2": "pt", "slug": "brazillian-portuguese", "country": "BR"},
    "pus": {"alpha2": "ps", "slug": "pashto"},
    "ron": {"alpha2": "ro", "slug": "romanian"},
    "rus": {"alpha2": "ru", "slug": "russian"},
    "sin": {"alpha2": "si", "slug": "sinhala"},
    "slk": {"alpha2": "sk", "slug": "slovak"},
    "slv": {"alpha2": "sl", "slug": "slovenian"},
    "sme": {"alpha2": "se", "slug": "northen-sami"},
    "snd": {"alpha2": "sd", "slug": "sindhi"},
    "som": {"alpha2": "so", "slug": "somali"},
    "spa": {"alpha2": "es", "slug": "spanish"},
    "sqi": {"alpha2": "sq", "slug": "albanian"},
    "srp": {"alpha2": "sr", "slug": "serbian"},
    "sun": {"alpha2": "su", "slug": "sundanese"},
    "swa": {"alpha2": "sw", "slug": "swahili"},
    "swe": {"alpha2": "sv", "slug": "swedish"},
    "tam": {"alpha2": "ta", "slug": "tamil"},
    "tat": {"alpha2": "tt", "slug": "tatar"},
    "tel": {"alpha2": "te", "slug": "telugu"},
    "tgl": {"alpha2": "tl", "slug": "tagalog"},
    "tha": {"alpha2": "th", "slug": "thai"},
    "tuk": {"alpha2": "tk", "slug": "turkmen"},
    "tur": {"alpha2": "tr", "slug": "turkish"},
    "ukr": {"alpha2": "uk", "slug": "ukranian"},
    "urd": {"alpha2": "ur", "slug": "urdu"},
    "uzb": {"alpha2": "uz", "slug": "uzbek"},
    "vie": {"alpha2": "vi", "slug": "vietnamese"},
    "yor": {"alpha2": "yo", "slug": "yoruba"},
    "zho": {"alpha2": "zh", "slug": "chinese-bg-code"},
}

SLUG_TO_LANGUAGE = {value["slug"]: (key, value) for key, value in LANGUAGE_SLUGS.items()}
ALIAS_ALPHA3 = {
    "cze": "ces",
    "dut": "nld",
    "fre": "fra",
    "ger": "deu",
    "gre": "ell",
    "ice": "isl",
    "per": "fas",
    "rum": "ron",
}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
_SXXEYY_RE = re.compile(r"\bs0*(?P<season>\d{1,2})\s*e0*(?P<episode>\d{1,3})\b", re.I)
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


class SubsarrProvider:
    def search(self, video, languages, config):
        base_url = _base_url(config)
        requested = _requested_languages(languages)
        if not requested:
            return []
        video = dict(video or {})
        if video.get("kind") not in {"movie", "episode"}:
            return []
        results = []
        seen = set()
        for requested_language in requested:
            params = _base_search_params(video, requested_language)
            matched = []
            imdb_id = _imdb_id(video)
            if imdb_id:
                imdb_params = dict(params)
                imdb_params["imdb_id"] = imdb_id
                if video.get("kind") == "movie" and video.get("year") is not None:
                    imdb_params["year"] = video["year"]
                matched = self._collect_matches(base_url, imdb_params, requested_language, config)
            title = _title(video)
            if not matched and title:
                title_params = dict(params)
                title_params["query"] = title
                matched = self._collect_matches(base_url, title_params, requested_language, config)
            for item, row_language in matched:
                result = self._result(video, item, row_language, base_url)
                key = (result["provider_payload"]["record_id"], result["language"]["alpha3"], result["language"]["hi"])
                if key in seen:
                    continue
                seen.add(key)
                results.append(result)
                if len(results) >= MAX_RESULTS:
                    return _sort_results(results)
        return _sort_results(results)

    def download(self, provider_payload, language, config):
        del language
        payload = dict(provider_payload or {})
        url = payload.get("download_url")
        if not url:
            raise ValueError("subsarr download requires download_url")
        _base_url(config)
        body = self._http_get_bytes(url, config=config)
        body = _normalize_line_endings(body)
        return _content_payload(body, _subtitle_extension(payload.get("filename")) or "srt")

    def _collect_matches(self, base_url, params, requested_language, config):
        # Subsarr only filters server-side when hi=true, so non-HI requests get a
        # mixed result set. Paginate before applying the local HI filter so rows of
        # the requested variant on later pages are not lost when the first page is
        # dominated by the other variant.
        matched = []
        for page in range(1, MAX_SEARCH_PAGES + 1):
            page_params = dict(params)
            page_params["page"] = page
            _sleep(config)
            items = self._search(base_url, page_params, config)
            for item in items:
                row_language = _language_from_slug(item.get("language"))
                if row_language is None:
                    continue
                if not _language_requested(row_language, requested_language, item):
                    continue
                matched.append((item, row_language))
            if len(items) < PER_PAGE:
                break
        return matched

    def _search(self, base_url, params, config):
        url = f"{base_url}/api/v1/subtitles/search?{urllib.parse.urlencode(params)}"
        payload = self._http_get_json(url, config=config)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return items if isinstance(items, list) else []

    def _http_get_json(self, url, timeout=HTTP_TIMEOUT_SECONDS, config=None):
        body = self._http_get_bytes(url, timeout=timeout, config=config)
        return json.loads(body.decode("utf-8"))

    def _http_get_bytes(self, url, timeout=HTTP_TIMEOUT_SECONDS, config=None):
        del config
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,*/*"})
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code < 500 or attempt == 2:
                    raise
                time.sleep(5)
            except urllib.error.URLError as error:
                last_error = error
                if attempt == 2:
                    raise
                time.sleep(5)
        if last_error:
            raise last_error
        return b""

    def _result(self, video, item, row_language, base_url):
        alpha3, meta = row_language
        is_hi = bool(item.get("hi"))
        releases = item.get("releases") if isinstance(item.get("releases"), list) else []
        filename = str(item.get("filename") or f"subsarr-{item.get('id', 'subtitle')}.srt")
        release_info = ", ".join(str(release) for release in releases if release) or filename
        matches = derive_matches(video, item.get("title"), release_info)
        score = 95 if "episode" in matches or "title" in matches else 80
        display_alpha3 = "por" if alpha3 == "por-BR" else alpha3
        country = meta.get("country")
        download_url = _download_url(base_url, item.get("download_url"))
        language_block = {
            "alpha3": display_alpha3,
            "alpha2": meta["alpha2"],
            "hi": is_hi,
            "forced": False,
        }
        if country:
            language_block["country_alpha2"] = country
        return {
            "provider": PROVIDER_ID,
            "id": f"subsarr-{item.get('id')}-{display_alpha3}-{country.lower() if country else 'xx'}-{'hi' if is_hi else 'normal'}",
            "language": language_block,
            "release_info": release_info,
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": True,
            "hearing_impaired": is_hi,
            "page_link": download_url,
            "display": {
                "source": "subsarr",
                "title": item.get("title"),
                "release": release_info,
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "record_id": str(item.get("id")),
                "download_url": download_url,
                "filename": filename,
                "language": display_alpha3,
                "country_alpha2": country,
                "language_slug": item.get("language"),
                "language_name": _language_name(alpha3),
                "hi": is_hi,
            },
        }


def language_slug(language):
    code = _language_code(language)
    if code == "por" and _country(language) == "BR":
        code = "por-BR"
    meta = LANGUAGE_SLUGS.get(code)
    return meta["slug"] if meta else None


def derive_matches(video, title, release_info):
    video = video or {}
    candidate = f"{title or ''} {release_info or ''}"
    tokens = set(_tokens(candidate))
    matches = []
    if video.get("kind") == "episode":
        series_tokens = _tokens(video.get("series"))
        if series_tokens and all(token in tokens for token in series_tokens):
            matches.append("series")
        season = _safe_int(video.get("season"))
        episode = _safe_int(video.get("episode"))
        if season is not None and _text_has_season(candidate, season):
            matches.append("season")
        if season is not None and episode is not None and _text_has_episode(candidate, season, episode):
            matches.append("episode")
    else:
        title_tokens = _tokens(video.get("title"))
        if title_tokens and all(token in tokens for token in title_tokens):
            matches.append("title")
        year = _safe_int(video.get("year"))
        if year is not None and str(year) in tokens:
            matches.append("year")
    return matches


def _base_url(config):
    base_url = str((config or {}).get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("subsarr base_url must be specified")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("subsarr base_url must include http:// or https://")
    return base_url


def _requested_languages(languages):
    requested = []
    seen = set()
    for language in languages or []:
        # Subsarr returns full subtitles and cannot verify forced status, so a
        # forced-only request must be skipped instead of surfacing regular subs.
        if isinstance(language, dict) and language.get("forced"):
            continue
        slug = language_slug(language)
        code = _language_code(language)
        if code == "por" and _country(language) == "BR":
            code = "por-BR"
        if not slug or code not in LANGUAGE_SLUGS:
            continue
        hi = bool(language.get("hi")) if isinstance(language, dict) else False
        key = (code, hi)
        if key in seen:
            continue
        seen.add(key)
        meta = dict(LANGUAGE_SLUGS[code])
        meta.update({"alpha3": code, "hi": hi, "name": _language_name(code)})
        requested.append(meta)
    return requested


def _language_from_slug(slug):
    value = str(slug or "").strip()
    if not value:
        return None
    row = SLUG_TO_LANGUAGE.get(value.lower())
    if row:
        return row
    normalized = value.casefold()
    for code, meta in LANGUAGE_SLUGS.items():
        if _language_name(code).casefold() == normalized:
            return code, meta
    return None


def _language_requested(row_language, requested_language, item):
    alpha3, meta = row_language
    if alpha3 != requested_language["alpha3"]:
        return False
    if meta.get("country") and meta.get("country") != requested_language.get("country"):
        return False
    return bool(item.get("hi")) == bool(requested_language.get("hi"))


def _base_search_params(video, requested_language):
    params = {
        "language": requested_language["slug"],
        "hi": "true" if requested_language.get("hi") else "false",
        "per_page": 100,
    }
    if video.get("kind") == "episode":
        if video.get("season") is not None:
            params["season"] = video["season"]
        if video.get("episode") is not None:
            params["episode"] = video["episode"]
    return params


def _download_url(base_url, download_url):
    if not download_url:
        return download_url
    base = urllib.parse.urlparse(base_url)
    parsed = urllib.parse.urlparse(str(download_url))
    base_path = base.path.rstrip("/")
    if not parsed.scheme and not parsed.netloc:
        # Relative URL: anchor on the configured base_url (scheme, host, prefix).
        return urllib.parse.urljoin(base_url.rstrip("/") + "/", str(download_url).lstrip("/"))
    # Absolute URL from the Subsarr response. Subsarr builds it from only scheme and
    # host (from the upstream request), so behind a TLS-terminating or path-prefixing
    # reverse proxy it can drop the configured scheme and prefix. Rebuild the scheme,
    # host, and prefix from the configured base_url while keeping the response path and
    # query (which may carry download tokens).
    path = parsed.path
    if base_path and not path.startswith(base_path + "/") and path != base_path:
        path = base_path + path
    return urllib.parse.urlunparse((base.scheme, base.netloc, path, parsed.params, parsed.query, parsed.fragment))


def _language_name(code):
    if code == "por-BR":
        return "Brazilian Portuguese"
    slug = LANGUAGE_SLUGS.get(code, {}).get("slug", str(code or ""))
    return slug.replace("-", " ").replace("_", " ").title()


def _imdb_id(video):
    return (video or {}).get("series_imdb_id") or (video or {}).get("imdb_id")


def _title(video):
    video = video or {}
    return video.get("series") if video.get("kind") == "episode" else video.get("title")


def _language_code(language):
    if isinstance(language, str):
        code = language
    elif isinstance(language, dict):
        code = language.get("alpha3") or language.get("code") or language.get("alpha2") or ""
    else:
        code = ""
    code = str(code)
    if code in LANGUAGE_SLUGS:
        return code
    code = code.lower()
    if len(code) == 2:
        for alpha3, meta in LANGUAGE_SLUGS.items():
            if meta["alpha2"] == code and alpha3 != "por-BR":
                return alpha3
    return ALIAS_ALPHA3.get(code, code)


def _country(language):
    if not isinstance(language, dict):
        return None
    value = language.get("country") or language.get("country_alpha2") or language.get("region")
    if not value and str(language.get("alpha3") or "").lower() in {"por-br", "pt-br"}:
        value = "BR"
    return str(value).upper() if value else None


def _sort_results(results):
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _text_has_season(text, season):
    normalized = _normalize(text)
    return bool(re.search(rf"\bs0*{season}\b|\bseason[\W_]+0*{season}\b", normalized))


def _text_has_episode(text, season, episode):
    for match in _SXXEYY_RE.finditer(_normalize(text)):
        if _safe_int(match.group("season")) == season and _safe_int(match.group("episode")) == episode:
            return True
    return False


def _normalize_line_endings(body):
    return (body or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _content_payload(body, extension, empty=False):
    data = body or b""
    return {
        "content_b64": base64.b64encode(data).decode("ascii"),
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "format": (extension or "srt").lstrip(".").lower(),
        "empty": bool(empty),
    }


def _subtitle_extension(name):
    lower_name = str(name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lower_name.endswith(extension):
            return extension.lstrip(".")
    return None


def _sleep(config):
    try:
        delay = int((config or {}).get("request_delay_ms") or 0)
    except (TypeError, ValueError):
        delay = 0
    if delay > 0:
        time.sleep(min(delay, 5000) / 1000.0)


def _tokens(value):
    normalized = _normalize(value)
    return [token for token in _NON_ALNUM_RE.split(normalized) if token]


def _normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return _WS_RE.sub(" ", value.lower()).strip()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
