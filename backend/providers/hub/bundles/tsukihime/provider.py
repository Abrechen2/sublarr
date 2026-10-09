"""TsukiHime anime subtitle provider for the Bazarr+ Provider Hub."""

import base64
import hashlib
import json
import lzma
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PROVIDER_ID = "tsukihime"
API_URL = "https://api.tsukihime.org/v1"
STORAGE_URL = "https://storage.tsukihime.org"
HTTP_TIMEOUT_SECONDS = 15
MAX_API_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_COMPRESSED_SUBTITLE_BYTES = 2 * 1024 * 1024
MAX_SUBTITLE_BYTES = 8 * 1024 * 1024
MAX_TORRENTS = 20
SUBTITLE_CODECS = {"ass", "srt", "ssa", "sub", "vtt"}
CONTENT_TYPES = {
    "ass": "text/x-ssa",
    "ssa": "text/x-ssa",
    "vtt": "text/vtt",
    "sub": "text/plain",
    "srt": "application/x-subrip",
}
USER_AGENT = "BazarrProviderHub"

ALPHA2_TO_ALPHA3 = {
    "af": "afr", "am": "amh", "ar": "ara", "az": "aze", "be": "bel",
    "bg": "bul", "bn": "ben", "bs": "bos", "ca": "cat", "cs": "ces",
    "da": "dan", "de": "deu", "el": "ell", "en": "eng", "eo": "epo",
    "es": "spa", "et": "est", "eu": "eus", "fa": "fas", "fi": "fin",
    "fr": "fra", "gl": "glg", "he": "heb", "hi": "hin", "hr": "hrv",
    "hu": "hun", "hy": "hye", "id": "ind", "is": "isl", "it": "ita",
    "ja": "jpn", "ka": "kat", "kk": "kaz", "ko": "kor", "lt": "lit",
    "lv": "lav", "mk": "mkd", "ms": "msa", "nl": "nld", "no": "nor",
    "pl": "pol", "pt": "por", "ro": "ron", "ru": "rus", "sk": "slk",
    "sl": "slv", "sq": "sqi", "sr": "srp", "sv": "swe", "th": "tha",
    "tr": "tur", "uk": "ukr", "ur": "urd", "uz": "uzb", "vi": "vie",
    "zh": "zho",
}
BIBLIOGRAPHIC_TO_CANONICAL = {
    "alb": "sqi", "arm": "hye", "baq": "eus", "bur": "mya", "chi": "zho",
    "cze": "ces", "dut": "nld", "fre": "fra", "geo": "kat", "ger": "deu",
    "gre": "ell", "ice": "isl", "mac": "mkd", "may": "msa", "mao": "mri",
    "per": "fas", "rum": "ron", "slo": "slk", "tib": "bod", "wel": "cym",
}
ALPHA3_TO_ALPHA2 = {value: key for key, value in ALPHA2_TO_ALPHA3.items()}
SUPPORTED_LANGUAGES = set(ALPHA2_TO_ALPHA3.values()) | {
    "mri", "mya", "bod", "cym"
}
REGIONAL_ALIASES = {
    "es-419": ("spa", "MX"),
    "es-es": ("spa", "ES"),
    "pt-br": ("por", "BR"),
    "pt-pt": ("por", "PT"),
    "zh-cn": ("zho", "CN"),
    "zh-hans": ("zho", "CN"),
    "zh-hk": ("zho", "TW"),
    "zh-hant": ("zho", "TW"),
    "zh-tw": ("zho", "TW"),
}
LANGUAGE_NAMES = {
    "afr": {"afrikaans"}, "ara": {"arabic"}, "bul": {"bulgarian"},
    "cat": {"catalan"}, "ces": {"czech"}, "deu": {"german"},
    "ell": {"greek"}, "eng": {"english"}, "spa": {"spanish"},
    "est": {"estonian"}, "fas": {"persian"}, "fin": {"finnish"},
    "fra": {"french"}, "heb": {"hebrew"}, "hin": {"hindi"},
    "hrv": {"croatian"}, "hun": {"hungarian"}, "ind": {"indonesian"},
    "isl": {"icelandic"}, "ita": {"italian"}, "jpn": {"japanese"},
    "kor": {"korean"}, "nld": {"dutch"}, "nor": {"norwegian"},
    "pol": {"polish"}, "por": {"portuguese"}, "ron": {"romanian"},
    "rus": {"russian"}, "slk": {"slovak"}, "slv": {"slovenian"},
    "srp": {"serbian"}, "swe": {"swedish"}, "tha": {"thai"},
    "tur": {"turkish"}, "ukr": {"ukrainian"}, "vie": {"vietnamese"},
    "zho": {"chinese", "chinese simplified", "chinese traditional"},
}

_HI_MARKER_RE = re.compile(
    r"(?:^|[\s_.\-\[(])(?:cc|sdh|hearing[\s_.\-]*impaired)(?:$|[\s_.\-)\]])",
    re.IGNORECASE,
)
# A standalone "HI" also marks hearing-impaired tracks, except on Hindi tracks,
# where "hi" is the language code.
_HI_CODE_MARKER_RE = re.compile(r"(?:^|[\s_.\-\[(])hi(?:$|[\s_.\-)\]])", re.IGNORECASE)
_SIGNS_MARKER_RE = re.compile(r"\bsigns?\b", re.IGNORECASE)
_SXXEYY_RE = re.compile(r"\bs0*(\d{1,3})\s*e0*(\d{1,4})\b", re.I)
_X_MARKER_RE = re.compile(r"\b(\d{1,3})x(\d{1,4})\b", re.I)
_EPISODE_RE = re.compile(r"(?:^|[^a-z0-9])e(?:pisode)?[ ._-]*0*(\d{1,4})(?:[^0-9]|$)", re.I)
# The usual anime batch name, "Show - 01 [1080p].mkv": a dash, then the number.
_DASH_EPISODE_RE = re.compile(r"(?:^|[\s_])-[\s_]*0*(\d{1,4})(?:v\d{1,2})?(?=$|[\s_.\[(])")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_XZ_MAGIC = b"\xfd7zXZ\x00"


def _redirect_origin(url):
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        return None
    return parts.scheme.lower(), parts.hostname.lower(), 443 if port is None else port


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow HTTPS redirects on the same origin or the observed storage mirror."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        source = _redirect_origin(request.full_url)
        target = _redirect_origin(new_url)
        allowed_storage_mirror = (
            source == ("https", "storage.tsukihime.org", 443)
            and target == ("https", "storage.animetosho.org", 443)
        )
        if source != target and not allowed_storage_mirror:
            return None
        return super().redirect_request(request, response, code, message, headers, new_url)


class TsukiHimeProvider:
    """Search TsukiHime's public API and download cached XZ subtitle tracks."""

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, max_bytes=MAX_API_RESPONSE_BYTES):
        _validate_provider_url(url)
        max_bytes = _positive_int(max_bytes) or MAX_API_RESPONSE_BYTES
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        opener = urllib.request.build_opener(_SameOriginRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("TsukiHime response exceeded the size limit")
        return body

    def _get_json(self, path):
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError("invalid TsukiHime API path")
        url = API_URL + path
        try:
            body = self._http_get(url, max_bytes=MAX_API_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(f"TsukiHime API returned HTTP {error.code}") from error
        if len(body) > MAX_API_RESPONSE_BYTES:
            raise ValueError("TsukiHime API response exceeded the size limit")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("TsukiHime returned invalid JSON") from error
        if not isinstance(data, (dict, list)):
            raise ValueError("TsukiHime returned an invalid JSON shape")
        return data

    def search(self, video, languages, config):
        del config
        video = video if isinstance(video, dict) else {}
        requested = _requested_languages(languages)
        if not requested:
            return []
        kind = video.get("kind")
        if kind == "episode":
            anidb_id = _positive_id(_scalar(video.get("series_anidb_id")))
            # The AniDB episode id gates the search, because it only exists
            # once the live AniDB API answered, but the episodes endpoint is
            # keyed by the episode number: queried with the AniDB episode id
            # it returns no torrents for any show, while the episode number
            # returns them.
            episode_id = _positive_id(_scalar(video.get("series_anidb_episode_id")))
            episode_no = _positive_id(_scalar(video.get("series_anidb_episode_no")))
            if anidb_id is None or episode_id is None or episode_no is None:
                return []
            anime = self._get_json(f"/animes/anidb/{anidb_id}")
            if not isinstance(anime, dict):
                return []
            anime_id = _positive_id(anime.get("id"))
            if anime_id is None:
                return []
            entries_data = self._get_json(f"/animes/{anime_id}/episodes/{episode_no}")
        elif kind == "movie":
            anilist_id = _positive_id(_scalar(video.get("anilist_id")))
            if anilist_id is None:
                return []
            anime = self._get_json(f"/animes/anilist/{anilist_id}")
            if not isinstance(anime, dict):
                return []
            anime_id = _positive_id(anime.get("id"))
            if anime_id is None:
                return []
            entries_data = self._get_json(f"/animes/{anime_id}")
        else:
            return []

        entries = _results(entries_data)
        entries = [
            entry for entry in entries
            if entry.get("state") == "completed"
            and _positive_id(entry.get("id")) is not None
            and _entry_has_requested_language(entry.get("sublangs"), requested)
        ]
        entries.sort(key=lambda entry: _entry_score(video, entry), reverse=True)

        results = []
        seen = set()
        for entry in entries[:MAX_TORRENTS]:
            entry_id = _positive_id(entry.get("id"))
            try:
                detail = self._get_json(f"/torrents/{entry_id}")
            except (OSError, RuntimeError, ValueError):
                continue
            if not isinstance(detail, dict):
                continue
            files = detail.get("files")
            if not isinstance(files, list):
                continue
            for file_data in _matching_files(video, files):
                for attachment in file_data.get("attachments") or []:
                    row = _subtitle_from_attachment(video, anime, entry, file_data, attachment, requested)
                    if row is None:
                        continue
                    result = _result(video, row)
                    if result["id"] in seen:
                        continue
                    seen.add(result["id"])
                    results.append(result)
        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload if isinstance(provider_payload, dict) else {}
        if payload.get("provider") not in (None, PROVIDER_ID):
            raise ValueError("TsukiHime download payload has the wrong provider")
        attachment_id = _positive_id(payload.get("attachment_id"))
        if attachment_id is None:
            raise ValueError("TsukiHime download requires a valid attachment id")
        codec = str(payload.get("format") or "srt").lower()
        if codec not in SUBTITLE_CODECS:
            raise ValueError("TsukiHime download format is unsupported")
        mirrored = bool(payload.get("animetosho"))
        storage_path = "tosho/attach" if mirrored else "attach"
        url = f"{STORAGE_URL}/{storage_path}/{attachment_id:08X}/{attachment_id}.xz"
        body = self._http_get(
            url,
            timeout=HTTP_TIMEOUT_SECONDS,
            max_bytes=MAX_COMPRESSED_SUBTITLE_BYTES,
        )
        if len(body) > MAX_COMPRESSED_SUBTITLE_BYTES:
            raise ValueError("TsukiHime compressed subtitle exceeded the size limit")
        if not body.startswith(_XZ_MAGIC):
            raise ValueError("TsukiHime returned an unidentified XZ archive")
        content = _bounded_xz_decompress(body)
        try:
            content.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "latin-1"
        return {
            "content_b64": base64.b64encode(content).decode("ascii"),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "content_type": CONTENT_TYPES[codec],
            "format": codec,
            "encoding": encoding,
            "empty": not bool(content),
        }


def _validate_provider_url(url):
    parts = urllib.parse.urlsplit(str(url))
    if (
        parts.scheme != "https"
        or parts.hostname not in {"api.tsukihime.org", "storage.tsukihime.org"}
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.fragment
    ):
        raise ValueError("TsukiHime URL is outside the provider endpoints")


def _scalar(value):
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _positive_id(value):
    if isinstance(value, bool):
        return None
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{1,18}", text):
        return None
    result = int(text)
    return result if result > 0 else None


def _season_number(value):
    if isinstance(value, bool):
        return None
    text = str(value if value is not None else "").strip()
    if not re.fullmatch(r"\d{1,3}", text):
        return None
    return int(text)


def _int_or_none(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _results(data):
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return [item for item in data["results"] if isinstance(item, dict)]
    return []


def _language_from_code(code, name=""):
    value = str(code or "").strip().lower().replace("_", "-")
    if not value:
        return None
    country = None
    if value in REGIONAL_ALIASES:
        alpha3, country = REGIONAL_ALIASES[value]
    else:
        base = value.split("-", 1)[0]
        alpha3 = ALPHA2_TO_ALPHA3.get(base, BIBLIOGRAPHIC_TO_CANONICAL.get(base, base))
        if alpha3 not in SUPPORTED_LANGUAGES:
            return None
        if "-" in value:
            region = value.split("-", 1)[1].upper()
            if region in {"BR", "PT", "ES", "MX", "CN", "TW", "HK"}:
                country = {"HK": "TW"}.get(region, region)
    normalized_name = str(name or "").lower()
    if alpha3 == "por" and ("brazil" in normalized_name or "brasil" in normalized_name):
        country = "BR"
    elif alpha3 == "por" and "portugal" in normalized_name:
        country = "PT"
    elif alpha3 == "spa" and any(term in normalized_name for term in ("latin america", "latin american", "latam")):
        country = "MX"
    elif alpha3 == "spa" and any(term in normalized_name for term in ("spain", "castilian")):
        country = "ES"
    elif alpha3 == "zho" and any(term in normalized_name for term in ("traditional", "hong kong", "taiwan")):
        country = "TW"
    elif alpha3 == "zho" and "simplified" in normalized_name:
        country = "CN"
    return {
        "alpha3": alpha3,
        "alpha2": ALPHA3_TO_ALPHA2.get(alpha3),
        "country_alpha2": country,
        "hi": False,
        "forced": False,
    }


def _requested_languages(languages):
    requested = []
    for item in languages or []:
        if not isinstance(item, dict):
            continue
        code = item.get("alpha3") or item.get("alpha2")
        language = _language_from_code(code)
        if not language:
            continue
        country = item.get("country_alpha2") or item.get("country") or item.get("region")
        if country:
            language["country_alpha2"] = str(country).upper()
        language["forced"] = _optional_bool(item, "forced")
        language["hi"] = _optional_bool(item, "hi", "hearing_impaired")
        requested.append(language)
    return requested


def _optional_bool(mapping, key, fallback=None):
    if key in mapping:
        value = mapping.get(key)
    elif fallback and fallback in mapping:
        value = mapping.get(fallback)
    else:
        return None
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _language_matches_request(language, requested):
    for item in requested:
        if item["alpha3"] != language["alpha3"]:
            continue
        country = item.get("country_alpha2")
        if country and country != language.get("country_alpha2"):
            continue
        for flag in ("forced", "hi"):
            wanted = item.get(flag)
            if wanted is not None and bool(language.get(flag)) != wanted:
                break
        else:
            return True
    return False


def _entry_has_requested_language(sublangs, requested):
    if not isinstance(sublangs, list) or not sublangs:
        return True
    requested_codes = {item["alpha3"] for item in requested}
    for code in sublangs:
        language = _language_from_code(code)
        if language and language["alpha3"] in requested_codes:
            return True
    return False


def _subtitle_from_attachment(video, anime, entry, file_data, attachment, requested):
    if not isinstance(attachment, dict) or attachment.get("type") not in (1, "1", "subtitle"):
        return None
    info = attachment.get("info") if isinstance(attachment.get("info"), dict) else {}
    if info.get("cached") == 0 or str(info.get("cached") or "").strip() == "0":
        return None
    language = _language_from_code(info.get("lang"), info.get("name"))
    if not language:
        return None
    track_name = str(info.get("name") or "")
    language["forced"] = _bool(info.get("forced")) or bool(_SIGNS_MARKER_RE.search(track_name))
    language["hi"] = bool(
        _HI_MARKER_RE.search(track_name)
        or (language["alpha3"] != "hin" and _HI_CODE_MARKER_RE.search(track_name))
    )
    if not _language_matches_request(language, requested):
        return None
    codec = str(info.get("codec") or "").lower()
    attachment_id = _positive_id(attachment.get("id"))
    release_id = _positive_id(entry.get("id"))
    if codec not in SUBTITLE_CODECS or attachment_id is None or release_id is None:
        return None
    storage_path = "tosho/attach" if entry.get("animetosho") else "attach"
    download_url = f"{STORAGE_URL}/{storage_path}/{attachment_id:08X}/{attachment_id}.xz"
    release_info = str(entry.get("name") or file_data.get("filename") or "").strip()
    if not release_info:
        release_info = str(entry.get("id"))
    difference = _streaming_service(release_info) or _track_label(track_name, language["alpha3"])
    if difference:
        release_info = f"[{difference}] {release_info}"

    matches = {"title"} if video.get("kind") == "movie" else {"series", "season", "episode"}
    year = _int_or_none(video.get("year"))
    release_year = _int_or_none(anime.get("release_year"))
    if year is not None and release_year == year:
        matches.add("year")
    key = (release_id, attachment_id, language["alpha3"], language.get("country_alpha2"), language["forced"], language["hi"])
    return {
        "entry_id": release_id,
        "attachment_id": attachment_id,
        "animetosho": bool(entry.get("animetosho")),
        "language": language,
        "format": codec,
        "filename": file_data.get("filename") or f"{attachment_id}.{codec}",
        "download_url": download_url,
        "release_info": release_info,
        "matches": sorted(matches),
        "identity": key,
    }


def _result(video, row):
    language = dict(row["language"])
    matches = list(row["matches"])
    score = 75 + (10 if "year" in matches else 0)
    identity = ":".join(str(value or "") for value in row["identity"])
    result_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return {
        "provider": PROVIDER_ID,
        "id": f"tsukihime-{result_id}",
        "language": language,
        "release_info": row["release_info"],
        "filename": row["filename"],
        "matches": matches,
        "score": score,
        "score_without_hash": score,
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": bool(language["hi"]),
        "page_link": row["download_url"],
        "format": row["format"],
        "display": {
            "source": "TsukiHime",
            "title": row["release_info"],
            "release": row["filename"],
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "release_id": row["entry_id"],
            "attachment_id": row["attachment_id"],
            "animetosho": row["animetosho"],
            "download_url": row["download_url"],
            "format": row["format"],
            "language": language,
        },
    }


def _matching_files(video, files):
    files = [item for item in files if isinstance(item, dict) and isinstance(item.get("attachments"), list)]
    if not files:
        return files
    if video.get("kind") == "movie":
        if len(files) <= 1:
            return files
        reference = os.path.splitext(str(video.get("original_name") or video.get("name") or video.get("title") or ""))[0]
        return [max(files, key=lambda item: _name_overlap(item.get("filename", ""), reference))]
    if video.get("kind") != "episode":
        return files
    episode = _positive_id(video.get("episode"))
    expected = {
        value for value in (
            _positive_id(_scalar(video.get("series_anidb_episode_no"))),
            episode,
        ) if value is not None
    }
    expected_season = _season_number(_scalar(video.get("season")))
    matching = []
    recognized = False
    for item in files:
        filename = str(item.get("filename") or "")
        season_episode = _SXXEYY_RE.search(filename)
        if season_episode:
            recognized = True
            file_season = int(season_episode.group(1))
            if (
                int(season_episode.group(2)) == episode
                and (expected_season is None or file_season == expected_season)
            ):
                matching.append(item)
            continue
        season_episode = _X_MARKER_RE.search(filename)
        if season_episode:
            recognized = True
            file_season = int(season_episode.group(1))
            if (
                int(season_episode.group(2)) == episode
                and (expected_season is None or file_season == expected_season)
            ):
                matching.append(item)
            continue
        episode_match = _EPISODE_RE.search(filename)
        if episode_match:
            recognized = True
            if int(episode_match.group(1)) in expected:
                matching.append(item)
            continue
        numbers = {int(match.group(1)) for match in _DASH_EPISODE_RE.finditer(filename)}
        if numbers:
            recognized = True
            if numbers & expected:
                matching.append(item)
    if matching:
        return matching
    # Markerless files are only trusted in a single-file torrent. In a batch
    # every file would be advertised as the requested episode.
    if recognized or len([item for item in files if item.get("attachments")]) > 1:
        return []
    return files


def _entry_score(video, entry):
    reference = video.get("original_name") or video.get("name") or video.get("series") or video.get("title") or ""
    return (_name_overlap(entry.get("name") or "", reference), _int_or_none(entry.get("source_date")) or 0)


def _name_overlap(candidate, reference):
    candidate_tokens = set(_TOKEN_RE.findall(str(candidate or "").lower()))
    reference_tokens = set(_TOKEN_RE.findall(str(reference or "").lower()))
    if not candidate_tokens or not reference_tokens:
        return 0.0
    return len(candidate_tokens & reference_tokens) / len(candidate_tokens)


def _streaming_service(value):
    lowered = str(value or "").lower()
    for pattern, name in (
        (r"\b(?:nf|netflix)\b", "Netflix"),
        (r"\b(?:cr|crunchyroll)\b", "Crunchy Roll"),
        (r"\b(?:amzn|amazon)\b", "Amazon Prime"),
        (r"\bdisney\+?\b", "Disney+"),
        (r"\bhulu\b", "Hulu"),
        (r"\bhidive\b", "HIDIVE"),
    ):
        if re.search(pattern, lowered):
            return name
    return None


def _track_label(name, alpha3):
    label = str(name or "").strip().strip("[]() ")
    if not label or label.lower() in LANGUAGE_NAMES.get(alpha3, set()):
        return None
    return label


def _bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_xz_decompress(body):
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
    chunks = []
    total = 0
    pending = body
    try:
        while True:
            chunk = decoder.decompress(pending, max_length=MAX_SUBTITLE_BYTES - total + 1)
            pending = b""
            total += len(chunk)
            if total > MAX_SUBTITLE_BYTES:
                raise ValueError("TsukiHime subtitle exceeded the decompressed size limit")
            chunks.append(chunk)
            if decoder.eof:
                if decoder.unused_data:
                    raise ValueError("TsukiHime subtitle contains trailing compressed data")
                return b"".join(chunks)
            if decoder.needs_input:
                raise ValueError("TsukiHime subtitle XZ stream is truncated")
    except lzma.LZMAError as error:
        raise ValueError("TsukiHime subtitle decompression failed") from error
