"""HDBits provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "hdbits"
TORRENTS_URL = "https://hdbits.org/api/torrents"
SUBTITLES_URL = "https://hdbits.org/api/subtitles"
DOWNLOAD_URL = "https://hdbits.org/getdox.php"
USER_AGENT = "BazarrProviderHub"
HTTP_TIMEOUT_SECONDS = 15
ALLOWED_EXTENSIONS = (".ass", ".srt", ".ssa", ".sub", ".vtt", ".zip", ".rar")
SUBTITLE_EXTENSIONS = (".ass", ".srt", ".ssa", ".sub", ".vtt")
BLOCKED_TOKENS = frozenset({"extra", "extras", "commentary", "lyrics"})
IDENTITY_MATCHES = frozenset({"tvdb_id", "imdb_id", "series", "title", "year", "season", "episode"})
# Matched against _normalize() output, so "S01.E01" arrives as "s01 e01". The
# second group keeps every episode of a multi-episode tag such as S01E01E02.
SEASON_EPISODE_TAG_RE = re.compile(
    r"\b(?:season\s*|s)(\d{1,3})((?:\s*(?:episode|ep|e)\s*\d{1,3})+)\b", re.I
)
# "5.1x265" normalizes to "5 1x265", so the x264 and x265 codecs are not episodes.
SEASON_X_EPISODE_RE = re.compile(r"\b(\d{1,2})x(?!26[45]\b)(\d{2,3})\b", re.I)
SEASON_TAG_RE = re.compile(r"\b(?:season\s*|s)(\d{1,3})\b", re.I)
# Lookarounds leave the separator between "e01 e02" free for the next marker.
LOOSE_EPISODE_RE = re.compile(r"(?<![a-z0-9])e(\d{1,3})(?![a-z0-9])", re.I)
# A range such as "S01E01-02", "1x01-02" or "E01-02" normalizes to an episode
# marker followed by the bare number that ends it.
EPISODE_RANGE_RE = re.compile(r"(?:(?<![a-z])(?:episode|ep|e)\s*|\dx)(\d{1,3})\s+(\d{1,3})(?=\s|$)", re.I)
# "E01-E10" is a range just as "E01-10" is, but it normalizes to the same text
# as the "E01E10" multi-episode tag. Dropping the second marker while the
# hyphen is still there keeps the two apart.
HYPHEN_RANGE_RE = re.compile(r"((?<![a-z])(?:episode|ep|e)\s*\d{1,3}\s*-\s*)(?:episode|ep|e)\s*(?=\d)", re.I)
# Audio layouts ("DDP5.1", "TrueHD 7.1") and codecs ("H.264") leave bare numbers
# behind after _normalize(), and none of them is an episode.
AUDIO_OR_CODEC_NUMBER_RE = re.compile(r"(?<![0-9])[1-9]\s[01](?=\s|$)|\b[hx]\s26[45]\b", re.I)
# Extracted tracks are named by their index ("2_English.srt"), which is never
# zero-padded, so "02_English.srt" still names episode 2.
TRACK_INDEX_RE = re.compile(r"^[1-9]\d?_")
# Disc rips name tracks by language ("3_English.HI.srt"), so a trailing "hi"
# after one of these words is the hearing-impaired tag, not Hindi.
SPELLED_LANGUAGE_NAMES = frozenset(
    {
        "arabic", "bulgarian", "catalan", "chinese", "croatian", "czech", "danish", "dutch",
        "english", "estonian", "finnish", "french", "german", "greek", "hebrew", "hungarian",
        "icelandic", "indonesian", "italian", "japanese", "korean", "latvian", "lithuanian",
        "malay", "norwegian", "persian", "polish", "portuguese", "romanian", "russian",
        "serbian", "slovak", "slovenian", "spanish", "swedish", "thai", "turkish",
        "ukrainian", "vietnamese",
    }
)


ALPHA2_TO_ALPHA3 = {
    "aa": "aar",
    "ab": "abk",
    "ae": "ave",
    "af": "afr",
    "ak": "aka",
    "am": "amh",
    "an": "arg",
    "ar": "ara",
    "as": "asm",
    "av": "ava",
    "ay": "aym",
    "az": "aze",
    "ba": "bak",
    "be": "bel",
    "bg": "bul",
    "bh": "bih",
    "bi": "bis",
    "bm": "bam",
    "bn": "ben",
    "bo": "bod",
    "bs": "bos",
    "ca": "cat",
    "ce": "che",
    "ch": "cha",
    "co": "cos",
    "cr": "cre",
    "cs": "ces",
    "cu": "chu",
    "cv": "chv",
    "cy": "cym",
    "da": "dan",
    "de": "deu",
    "dv": "div",
    "dz": "dzo",
    "ee": "ewe",
    "el": "ell",
    "en": "eng",
    "eo": "epo",
    "es": "spa",
    "et": "est",
    "eu": "eus",
    "fa": "fas",
    "ff": "ful",
    "fi": "fin",
    "fj": "fij",
    "fo": "fao",
    "fr": "fra",
    "fy": "fry",
    "ga": "gle",
    "gd": "gla",
    "gl": "glg",
    "gn": "grn",
    "gu": "guj",
    "gv": "glv",
    "ha": "hau",
    "he": "heb",
    "hi": "hin",
    "ho": "hmo",
    "hr": "hrv",
    "ht": "hat",
    "hu": "hun",
    "hy": "hye",
    "hz": "her",
    "ia": "ina",
    "id": "ind",
    "ie": "ile",
    "ig": "ibo",
    "ii": "iii",
    "ik": "ipk",
    "io": "ido",
    "is": "isl",
    "it": "ita",
    "iu": "iku",
    "ja": "jpn",
    "jv": "jav",
    "ka": "kat",
    "kg": "kon",
    "ki": "kik",
    "kj": "kua",
    "kk": "kaz",
    "kl": "kal",
    "km": "khm",
    "kn": "kan",
    "ko": "kor",
    "kr": "kau",
    "ks": "kas",
    "ku": "kur",
    "kv": "kom",
    "kw": "cor",
    "ky": "kir",
    "la": "lat",
    "lb": "ltz",
    "lg": "lug",
    "li": "lim",
    "ln": "lin",
    "lo": "lao",
    "lt": "lit",
    "lu": "lub",
    "lv": "lav",
    "mg": "mlg",
    "mh": "mah",
    "mi": "mri",
    "mk": "mkd",
    "ml": "mal",
    "mn": "mon",
    "mr": "mar",
    "ms": "msa",
    "mt": "mlt",
    "my": "mya",
    "na": "nau",
    "nb": "nob",
    "nd": "nde",
    "ne": "nep",
    "ng": "ndo",
    "nl": "nld",
    "nn": "nno",
    "no": "nor",
    "nr": "nbl",
    "nv": "nav",
    "ny": "nya",
    "oc": "oci",
    "oj": "oji",
    "om": "orm",
    "or": "ori",
    "os": "oss",
    "pa": "pan",
    "pi": "pli",
    "pl": "pol",
    "ps": "pus",
    "pt": "por",
    "qu": "que",
    "rm": "roh",
    "rn": "run",
    "ro": "ron",
    "ru": "rus",
    "rw": "kin",
    "sa": "san",
    "sc": "srd",
    "sd": "snd",
    "se": "sme",
    "sg": "sag",
    "si": "sin",
    "sk": "slk",
    "sl": "slv",
    "sm": "smo",
    "sn": "sna",
    "so": "som",
    "sq": "sqi",
    "sr": "srp",
    "ss": "ssw",
    "st": "sot",
    "su": "sun",
    "sv": "swe",
    "sw": "swa",
    "ta": "tam",
    "te": "tel",
    "tg": "tgk",
    "th": "tha",
    "ti": "tir",
    "tk": "tuk",
    "tl": "fil",
    "tn": "tsn",
    "to": "ton",
    "tr": "tur",
    "ts": "tso",
    "tt": "tat",
    "tw": "twi",
    "ty": "tah",
    "ug": "uig",
    "uk": "ukr",
    "ur": "urd",
    "uz": "uzb",
    "ve": "ven",
    "vi": "vie",
    "vo": "vol",
    "wa": "wln",
    "wo": "wol",
    "xh": "xho",
    "yi": "yid",
    "yo": "yor",
    "za": "zha",
    "zh": "zho",
    "zu": "zul",
}
ALPHA3_TO_ALPHA2 = {value: key for key, value in ALPHA2_TO_ALPHA3.items()}
ALPHA3_TO_ALPHA2.update({"eng": "en", "ell": "el", "por": "pt"})
SPECIAL_HDBITS_LANGUAGE = {
    "br": ("por", "BR"),
    "gr": ("ell", None),
    "uk": ("eng", None),
}
# HDBits uses "uk" for English, which leaves no known code for Ukrainian, so
# only languages some HDBits code resolves to are advertised.
HDBITS_LANGUAGES = sorted(
    {alpha3 for code, alpha3 in ALPHA2_TO_ALPHA3.items() if code not in SPECIAL_HDBITS_LANGUAGE}
    | {language for language, _country in SPECIAL_HDBITS_LANGUAGE.values()}
)

SOURCE_TOKENS = {
    "Blu-ray": ["bluray", "blueray", "brrip", "bdrip", "bd"],
    "Web": ["web", "webrip", "webdl", "web-dl"],
    "WEB-DL": ["webdl", "web-dl", "web"],
    "WEBRip": ["webrip", "web-rip", "web"],
    "HDTV": ["hdtv"],
    "DVD": ["dvd", "dvdrip"],
}
VIDEO_CODEC_TOKENS = {
    "H.264": ["h264", "x264"],
    "H.265": ["h265", "x265", "hevc"],
    "DivX": ["divx"],
    "XviD": ["xvid"],
}
LONG_FIELD_TOKENS = {
    "audio_codec": ("audio_codec",),
    "release_group": ("release_group",),
    "streaming_service": ("streaming_service",),
    "edition": ("edition",),
}


def _coerce_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        joined = " ".join(str(item) for item in value if item not in (None, ""))
        return joined or None
    return str(value)


def _normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", (_coerce_text(value) or "").lower()).strip()


def _tokens(value):
    return [item for item in _normalize(value).split(" ") if item]


def _release_tokens(value):
    return set(_tokens(value))


def _has_any_token(release_tokens, candidates):
    for candidate in candidates:
        chunks = _tokens(candidate)
        if chunks and all(chunk in release_tokens for chunk in chunks):
            return True
    return False


def _field_present(release_tokens, value):
    chunks = _tokens(value)
    return bool(chunks) and all(chunk in release_tokens for chunk in chunks)


def _ordered_unique(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def build_lookup(video):
    video = video or {}
    kind = video.get("kind")
    if kind == "movie":
        imdb_id = str(video.get("imdb_id") or video.get("imdb") or "").strip().removeprefix("tt")
        if not imdb_id:
            return {}, [], None
        return {"imdb": {"id": imdb_id}}, ["imdb_id", "title", "year"], None
    if kind == "episode":
        tvdb_id = video.get("series_tvdb_id") or video.get("tvdb_id") or video.get("tvdb")
        if tvdb_id in (None, "", 0):
            return {}, [], None
        lookup = {"tvdb": {"id": tvdb_id, "season": video.get("season")}}
        return lookup, ["tvdb_id", "imdb_id", "series", "title", "season", "episode"], video.get("episode")
    return {}, [], None


def hdbits_language(code):
    """Resolve an HDBits language code to ``(alpha3, country_alpha2)``."""
    normalized = str(code or "").lower().strip()
    special = SPECIAL_HDBITS_LANGUAGE.get(normalized)
    if special is not None:
        return special
    alpha3 = ALPHA2_TO_ALPHA3.get(normalized)
    if alpha3:
        return (alpha3, None)
    return (None, None)


def hdbits_language_to_alpha3(code):
    return hdbits_language(code)[0]


def _requested_alpha3(languages):
    return {key[0] for key in _requested_variant_map(languages)}


def _requested_variant_map(languages):
    if isinstance(languages, dict):
        return {_variant_key(key): set(value) for key, value in languages.items()}
    requested = {}
    for language in languages or []:
        key = _language_key(language)
        if key[0]:
            forced = bool(language.get("forced")) if isinstance(language, dict) else False
            hi = bool(language.get("hi")) if isinstance(language, dict) else False
            requested.setdefault(key, set()).add((hi, forced))
    return requested


def _variant_key(key):
    if isinstance(key, tuple):
        alpha3 = str(key[0]).lower() if key[0] else None
        country = str(key[1]).upper() if len(key) > 1 and key[1] else None
        return (alpha3, country)
    return (str(key).lower(), None)


def _language_key(language):
    if isinstance(language, dict):
        alpha3 = language.get("alpha3")
        alpha2 = language.get("alpha2")
        country = language.get("country_alpha2") or language.get("country")
    else:
        alpha3 = str(language)
        alpha2 = None
        country = None
    if not alpha3 and alpha2:
        alpha3 = ALPHA2_TO_ALPHA3.get(str(alpha2).lower())
    if not alpha3:
        return (None, None)
    return (str(alpha3).lower(), str(country).upper() if country else None)


def _language_alpha3(language):
    return _language_key(language)[0]


def _is_allowed(row):
    tokens = set(_tokens(f"{row.get('title') or ''} {row.get('filename') or ''}"))
    return not (tokens & BLOCKED_TOKENS)


def _subtitle_flags(row, language=None):
    tokens = set(_tokens(f"{row.get('title') or ''} {row.get('filename') or ''}"))
    forced = "forced" in tokens
    hi_tokens = {"sdh"}
    # For Hindi rows the "hi" token is the language code, not an accessibility flag.
    if language != "hin":
        hi_tokens.add("hi")
    hearing_impaired = bool(hi_tokens & tokens) or {"hearing", "impaired"}.issubset(tokens)
    return hearing_impaired, forced


def _subtitle_extension(filename):
    lowered = (filename or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _format_from_filename(filename):
    extension = _subtitle_extension(filename)
    if extension:
        return extension
    return "srt"


def _episode_markers(title):
    """Return the ``(season, episode)`` markers in a name.

    ``S01E01``, ``S01.E01``, ``1x01`` and ``Season 1 Episode 1`` name a season.
    A loose ``E01`` marker carries no season, so its season is ``None``.
    """
    normalized = _normalize(title)
    markers = {
        (int(match.group(1)), int(episode))
        for match in SEASON_EPISODE_TAG_RE.finditer(normalized)
        for episode in re.findall(r"\d+", match.group(2))
    }
    markers.update(
        (int(match.group(1)), int(match.group(2)))
        for match in SEASON_X_EPISODE_RE.finditer(normalized)
    )
    if markers:
        return markers
    return {(None, int(match.group(1))) for match in LOOSE_EPISODE_RE.finditer(normalized)}


def _names_episode(markers, season, episode):
    return any(
        marker_episode == episode
        and (marker_season is None or season is None or marker_season == season)
        for marker_season, marker_episode in markers or ()
    )


def _spans_episode(name, season, episode, between=True):
    """True when a name gives the episode for the season.

    A multi-episode tag such as "S01E01E02" gives each episode it lists and no
    other. A range such as "S01E01-02", "1x01-10" or "S01E01-E10" gives its
    first and last episode. With ``between`` the episodes between them count
    too, since a torrent or an archive holds each of them. One subtitle file
    answers only the episodes it lists.
    """
    if episode is None:
        return False
    markers = _episode_markers(name)
    if _names_episode(markers, season, episode):
        return True
    for first, last in EPISODE_RANGE_RE.findall(_loose_episode_text(name)):
        first, last = int(first), int(last)
        if first >= last:
            continue
        seasons = {marker_season for marker_season, marker_episode in markers if marker_episode == first}
        for marker_season in seasons or {marker_season for marker_season, _episode in markers} or {None}:
            if marker_season is not None and season is not None and marker_season != season:
                continue
            if first <= episode <= last if between else episode in (first, last):
                return True
    return False


def derive_matches(video, release_info, base_matches=None):
    matches = list(base_matches or [])
    release = release_info or ""
    release_tokens = _release_tokens(release)

    source = _coerce_text((video or {}).get("source"))
    if source:
        source_tokens = SOURCE_TOKENS.get(source)
        if source_tokens and _has_any_token(release_tokens, source_tokens):
            matches.append("source")
        elif source_tokens is None and _field_present(release_tokens, source):
            matches.append("source")

    resolution = _coerce_text((video or {}).get("resolution"))
    if resolution and resolution.lower() in release_tokens:
        matches.append("resolution")

    video_codec = _coerce_text((video or {}).get("video_codec"))
    if video_codec:
        codec_tokens = VIDEO_CODEC_TOKENS.get(video_codec)
        if codec_tokens and _has_any_token(release_tokens, codec_tokens):
            matches.append("video_codec")
        elif codec_tokens is None and _field_present(release_tokens, video_codec):
            matches.append("video_codec")

    for field_names in LONG_FIELD_TOKENS.values():
        field_name = field_names[0]
        value = _coerce_text((video or {}).get(field_name))
        if value and _field_present(release_tokens, value):
            matches.append(field_name)

    return _ordered_unique(matches)


def parse_subtitles(rows, requested_alpha3, video, base_matches, episode=None, torrent_markers=None):
    parsed = []
    requested = _requested_variant_map(requested_alpha3)
    wanted_season = _safe_nonnegative_int((video or {}).get("season"))
    for row in rows or []:
        filename = str(row.get("filename") or "")
        if not filename.lower().endswith(ALLOWED_EXTENSIONS):
            continue
        if not _is_allowed(row):
            continue
        language, country = hdbits_language(row.get("language"))
        if not language:
            continue
        variants = set(requested.get((language, country), ()))
        if country:
            # The manifest declares only base codes, so the host sends a generic
            # request (por) and a regional row (br, as por-BR) must still answer it.
            variants |= requested.get((language, None), set())
        if not variants:
            continue
        hearing_impaired, forced = _subtitle_flags(row, language)
        if (hearing_impaired, forced) not in variants:
            continue
        if episode is not None:
            name = f"{row.get('title') or ''} {filename}"
            markers = _episode_markers(name)
            try:
                wanted_episode = int(episode)
            except (TypeError, ValueError):
                wanted_episode = None
            archive = filename.lower().endswith((".zip", ".rar"))
            if markers and not _spans_episode(name, wanted_season, wanted_episode, between=archive):
                continue
            # An unnumbered row is only trusted when its torrent names the episode;
            # an archive is checked again when the host selects its member.
            if (
                not markers
                and not _names_episode(torrent_markers, wanted_season, wanted_episode)
                and not archive
            ):
                continue
        release_info = str(row.get("title") or filename)
        subtitle_id = row.get("id")
        parsed.append(
            {
                "subtitle_id": subtitle_id,
                "language": language,
                "country_alpha2": country,
                "release_info": release_info,
                "filename": filename,
                "matches": derive_matches(video, release_info, base_matches),
                "hearing_impaired": hearing_impaired,
                "forced": forced,
            }
        )
    return parsed


def _require_config(config):
    config = dict(config or {})
    username = str(config.get("username") or "").strip()
    passkey = str(config.get("passkey") or "").strip()
    if not username:
        raise ValueError("hdbits username is required")
    if not passkey:
        raise ValueError("hdbits passkey is required")
    return username, passkey


def _content_payload(content, subtitle_format, empty=False):
    content = content or b""
    return {
        "content_b64": _base64.b64encode(content).decode("ascii"),
        "content_sha256": _hashlib.sha256(content).hexdigest(),
        "content_type": _content_type(subtitle_format),
        "format": subtitle_format,
        "empty": bool(empty),
    }


def _content_type(subtitle_format):
    if subtitle_format in {"ass", "ssa"}:
        return "text/x-ssa"
    if subtitle_format == "vtt":
        return "text/vtt"
    if subtitle_format == "sub":
        return "text/plain"
    return "application/x-subrip"


def _safe_nonnegative_int(value):
    if type(value) is int:
        return value if value >= 0 else None
    if not isinstance(value, str) or not value.strip().isdigit():
        return None
    return int(value.strip())


def _delay(config):
    try:
        delay_ms = int((config or {}).get("request_delay_ms") or 0)
    except (TypeError, ValueError):
        delay_ms = 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


class HDBitsProvider:
    def search(self, video, languages, config):
        username, passkey = _require_config(config)
        requested = _requested_variant_map(languages)
        if not requested:
            return []

        lookup, base_matches, episode = build_lookup(video)
        if not lookup:
            return []

        auth = {"username": username, "passkey": passkey}
        torrents = self._post_json(TORRENTS_URL, {**auth, **lookup})
        torrent_items = [item for item in _api_data(torrents, "HDBits torrent lookup") if item.get("id") is not None]
        results = []
        for item in torrent_items:
            torrent_id = item.get("id")
            torrent_markers = _episode_markers(item.get("name"))
            if (
                episode is not None
                and torrent_markers
                and not _spans_episode(
                    item.get("name"),
                    _safe_nonnegative_int((video or {}).get("season")),
                    _safe_nonnegative_int(episode),
                )
            ):
                continue
            _delay(config)
            subtitles = self._post_json(SUBTITLES_URL, {**auth, "torrent_id": torrent_id})
            rows = parse_subtitles(
                _api_data(subtitles, "HDBits subtitles lookup"),
                requested_alpha3=requested,
                video=video,
                base_matches=base_matches,
                episode=episode,
                torrent_markers=torrent_markers,
            )
            for row in rows:
                results.append(self._result(video, row, torrent_id, episode))
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def download(self, provider_payload, language, config):
        del language
        _username, passkey = _require_config(config)
        payload = provider_payload or {}
        subtitle_id = payload.get("subtitle_id")
        if subtitle_id is None:
            raise ValueError("hdbits download requires subtitle_id")
        query = urllib.parse.urlencode({"id": subtitle_id, "passkey": passkey})
        body = self._http_get(f"{DOWNLOAD_URL}?{query}")
        if not body:
            raise RuntimeError("hdbits download returned an empty response")
        return download_payload(body, payload)

    def select_archive_member(self, provider_payload, language, members, config):
        del config
        payload = dict(provider_payload or {})
        if isinstance(language, dict):
            host_language = {
                key: value
                for key, value in language.items()
                if value not in (None, "")
            }
            if host_language:
                provider_language = payload.get("language")
                if isinstance(provider_language, dict):
                    requested_language = dict(provider_language)
                elif provider_language:
                    requested_language = {"alpha3": provider_language}
                else:
                    requested_language = {}
                requested_language.update(host_language)
                if not (requested_language.get("country_alpha2") or requested_language.get("country")):
                    provider_country = payload.get("country_alpha2")
                    if provider_country:
                        requested_language["country_alpha2"] = provider_country
                payload["language"] = requested_language
        elif language:
            payload["language"] = language
        try:
            member = select_subtitle_file(members, payload)
        except ValueError:
            return {"decision": "reject"}
        return {"decision": "pin", "member": member}

    def _result(self, video, row, torrent_id, episode):
        language = row["language"]
        alpha2 = ALPHA3_TO_ALPHA2.get(language, language[:2])
        country = row.get("country_alpha2")
        matches = row["matches"]
        # Every result shares the identity matches from the ID lookup, so only
        # release matches (source, resolution, codec, group, ...) rank them.
        release_matches = [match for match in matches if match not in IDENTITY_MATCHES]
        score = min(100, 70 + len(release_matches) * 5)
        language_payload = {
            "alpha3": language,
            "alpha2": alpha2,
            "hi": row.get("hearing_impaired", False),
            "forced": row.get("forced", False),
        }
        if country:
            language_payload["country_alpha2"] = country
        return {
            "provider": PROVIDER_ID,
            "id": f"hdbits-{row['subtitle_id']}",
            "language": language_payload,
            "release_info": row["release_info"],
            "filename": row["filename"],
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": True,
            "hearing_impaired": row.get("hearing_impaired", False),
            "page_link": "https://hdbits.org/",
            "display": {
                "source": "hdbits",
                "release": row["release_info"],
                "torrent_id": torrent_id,
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": row["subtitle_id"],
                "torrent_id": torrent_id,
                "filename": row["filename"],
                "season": (video or {}).get("season"),
                "episode": episode,
                "language": language,
                "country_alpha2": country,
                "hi": row.get("hearing_impaired", False),
                "forced": row.get("forced", False),
            },
        }

    def _post_json(self, url, payload, timeout=HTTP_TIMEOUT_SECONDS):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("hdbits API did not return JSON") from exc

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()


def download_payload(body, payload):
    payload = payload or {}
    filename = payload.get("filename") or ""
    if not body:
        raise RuntimeError("hdbits download returned an empty response")
    if _looks_like_html(body):
        raise RuntimeError("hdbits download returned an HTML page instead of a subtitle")
    if _is_archive_download(body, filename):
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "season": _safe_nonnegative_int(payload.get("season")),
            "episode": _safe_nonnegative_int(payload.get("episode")),
            "select_member": True,
        }
    return _content_payload(body, _format_from_filename(filename))


def _is_archive_download(body, filename):
    lowered = str(filename or "").lower()
    return (
        lowered.endswith((".zip", ".rar"))
        or zipfile.is_zipfile(io.BytesIO(body))
        or _is_rar_archive(body)
    )


def select_subtitle_file(names, payload):
    candidates = [name for name in names if _subtitle_extension(name)]
    if not candidates:
        raise ValueError("hdbits archive contains no supported subtitle files")
    try:
        season = int((payload or {}).get("season"))
    except (TypeError, ValueError):
        season = None
    try:
        episode = int((payload or {}).get("episode"))
    except (TypeError, ValueError):
        episode = None
    variant_rank = _variant_ranker(payload)
    if episode is None:
        return _best_language_candidate(candidates, payload, variant_rank)

    hints = _language_hints((payload or {}).get("language"))

    def score(name):
        value = _member_episode_score(name, season, episode)
        if hints & set(_tokens(name)):
            value += 20
        return value

    # Only keep files that actually carry the requested episode so a season pack
    # missing that episode raises instead of returning an arbitrary wrong file.
    matching = [name for name in candidates if _member_episode_score(name, season, episode) > 0]
    if not matching:
        raise ValueError(
            f"hdbits archive does not contain the requested episode {episode}"
        )

    return max(
        _language_candidates(matching, payload),
        key=lambda name: (score(name), variant_rank(name)),
    )


def _member_episode_score(name, season, episode):
    """Score how surely an archive member holds the requested episode, 0 if not.

    The file name decides first. Folders only fill in what it leaves out, as in
    "Season 2/Show.E01.srt" or "Subs/Show.S01E01/2_English.srt". Another season
    always rejects the member. A file name that names another episode only holds
    the requested one through a range such as "S01E01-02".
    """
    parts = [part for part in re.split(r"[\\/]", name) if part]
    basename, folders = parts[-1], parts[-2::-1]
    markers = _episode_markers(basename)
    marker_seasons = {marker_season for marker_season, _episode in markers} - {None}
    if marker_seasons:
        if _names_episode(markers, season, episode):
            # Without a requested season the marker is no surer than a bare E01.
            return 100 if season is not None else 90
        if season is not None and season not in marker_seasons:
            return 0
    else:
        member_season = _stated_season([basename, *folders])
        if season is not None and member_season is not None and member_season != season:
            return 0
        if markers:
            if _names_episode(markers, season, episode):
                return 90
        else:
            folder = next((part for part in folders if _episode_markers(part)), None)
            if folder is not None:
                # A folder for one video lists every episode it holds
                # ("Show.S01E01E02/"), while a pack names only its first and
                # last ("Show.S01E01-E10/").
                listed = _listed_episodes(folder)
                first, last = min(listed), max(listed)
                pack = last - first + 1 > len(listed)
                # A range with no gap ("Show.S01E01-E02/") is a pack of those
                # episodes or one double-episode video, since some tools name a
                # single multi-episode file that way too.
                paired = not pack and any(
                    int(start) < int(end) for start, end in EPISODE_RANGE_RE.findall(_loose_episode_text(folder))
                )
                # Every episode of a pack would reuse the same track index, so
                # there a leading number names the episode ("05_English.srt").
                name_text = basename if pack or paired else TRACK_INDEX_RE.sub("", basename)
                numbers = {int(token) for token in _loose_episode_text(name_text).split() if token.isdigit()}
                # A file name number among the folder's episodes picks one.
                picked = {number for number in numbers if first <= number <= last}
                if picked:
                    if episode in picked:
                        return 85
                    # In one double-episode video the number is a track index,
                    # so the member ranks below the one naming the episode but
                    # still answers it.
                    return 80 if paired and first <= episode <= last else 0
                if pack:
                    return 0
                # Otherwise the folder decides, because a bare number in the file
                # name is usually a track index ("Show.S01E01/2_English.srt").
                folder_names_episode = _names_episode(_episode_markers(folder), season, episode)
                return 85 if folder_names_episode or _range_reaches(_loose_episode_text(folder), episode) else 0
    loose = _loose_episode_text(basename)
    if markers:
        return 80 if _range_reaches(loose, episode) else 0
    # Loose fallback: a standalone episode-number token (for example
    # "Show 1 en srt"). It must be its own token so the season digits in
    # "s01e02" never satisfy an S01E01 request.
    if re.search(rf"(?:^|\s)0*{episode}(?:\s|$)", loose):
        return 80
    return 0


def _loose_episode_text(value):
    """Normalize a name without the bare numbers that are never an episode.

    Season tags ("Season 1"), audio layouts ("DDP5.1") and codecs ("H.264")
    all leave such numbers behind. A range keeps its shape, so "E01-E10" reads
    as "e01 10", the same as "E01-10".
    """
    text = re.sub(r"[^a-z0-9-]+", " ", (_coerce_text(value) or "").lower())
    text = HYPHEN_RANGE_RE.sub(r"\1", text)
    return AUDIO_OR_CODEC_NUMBER_RE.sub(" ", SEASON_TAG_RE.sub(" ", _normalize(text)))


def _listed_episodes(value):
    """Return the episodes a name gives, both ends of a range such as "S01E01-10" included."""
    episodes = {marker_episode for _season, marker_episode in _episode_markers(value)}
    for first, last in EPISODE_RANGE_RE.findall(_loose_episode_text(value)):
        episodes.update((int(first), int(last)))
    return episodes


def _range_reaches(normalized, episode):
    """True when a range such as "s01e01 02" runs on to the episode."""
    return any(int(first) < episode == int(last) for first, last in EPISODE_RANGE_RE.findall(normalized))


def _stated_season(parts):
    """Return the season named by the first part that names one.

    A part that names more than one season is ambiguous and gives no season.
    """
    for part in parts:
        seasons = {int(value) for value in SEASON_TAG_RE.findall(_normalize(part))}
        seasons.update(
            marker_season
            for marker_season, _episode in _episode_markers(part)
            if marker_season is not None
        )
        if seasons:
            return seasons.pop() if len(seasons) == 1 else None
    return None


def _variant_ranker(payload):
    """Rank archive members by how well their HI and forced tags fit the request.

    The rank only breaks ties between members that already match the episode
    and language, so an archive without variant tags still answers every
    request. The host language wins over the flags stored at search time.
    """
    payload = payload or {}
    language = payload.get("language")
    requested = language if isinstance(language, dict) else {}
    wanted = []
    for key in ("hi", "forced"):
        value = requested.get(key)
        wanted.append(bool(payload.get(key) if value is None else value))
    wanted_hi, wanted_forced = wanted
    alpha3 = _language_details(language)[0]

    def rank(name):
        # Packs may keep each variant in its own folder ("SDH/Show.S01E01.srt"),
        # and not always the nearest one ("Forced/Season 1/Show.S01E01.srt").
        parts = [part for part in re.split(r"[\\/]", name) if part]
        folders = " ".join(parts[:-1])
        hearing_impaired, forced = _subtitle_flags({"title": folders, "filename": parts[-1]}, alpha3)
        hearing_impaired = hearing_impaired or _has_trailing_cc_tag(parts[-1])
        # A forced file carries only part of the dialogue, so matching the
        # forced flag counts before matching the hearing-impaired one.
        return (forced == wanted_forced, hearing_impaired == wanted_hi)

    return rank


def _has_trailing_cc_tag(name):
    """True when "cc" (closed captions) sits among the trailing tags of a name.

    Only the tags after the title count, because "CC" inside a release name
    usually marks a Criterion release.
    """
    tokens = _tokens(os.path.splitext(os.path.basename(name))[0])
    known = set(ALPHA2_TO_ALPHA3) | set(ALPHA3_TO_ALPHA2) | set(SPECIAL_HDBITS_LANGUAGE) | SPELLED_LANGUAGE_NAMES
    for token in reversed(tokens[1:]):
        if token == "cc":
            return True
        if token not in known and token not in {"forced", "sdh"}:
            return False
    return False


def _best_language_candidate(candidates, payload, variant_rank):
    return max(_language_candidates(candidates, payload), key=variant_rank)


def _language_candidates(candidates, payload):
    language = (payload or {}).get("language")
    hints = _language_hints(language)
    if not hints:
        return candidates

    alpha3, _alpha2, country = _language_details(language)
    country = country or str((payload or {}).get("country_alpha2") or "").upper()
    if alpha3 == "por":
        codes_by_name = {name: _filename_language_codes(name) for name in candidates}
        regions_by_name = {name: _filename_language_region(name) for name in candidates}
        generic = [
            name
            for name, codes in codes_by_name.items()
            if codes & {"por", "pt"} and regions_by_name[name] is None and "br" not in codes
        ]
        brazilian = [
            name
            for name, codes in codes_by_name.items()
            if regions_by_name[name] == "BR" or (regions_by_name[name] is None and codes == {"br"})
        ]
        european = [name for name, region in regions_by_name.items() if region == "PT"]
        unlabelled = [name for name, codes in codes_by_name.items() if not codes]

        if country == "BR":
            if brazilian:
                return brazilian
            if generic:
                return generic
        elif country == "PT":
            if european:
                return european
            if generic:
                return generic
        elif not country:
            if european:
                return european
            if generic:
                return generic

        if unlabelled:
            return unlabelled
        raise ValueError("hdbits archive does not contain the requested language")

    matching = [name for name in candidates if hints & _filename_language_codes(name)]
    if matching:
        return matching
    unlabelled = [name for name in candidates if not _filename_language_codes(name)]
    if unlabelled:
        return unlabelled
    raise ValueError("hdbits archive does not contain the requested language")


def _filename_language_codes(name):
    # Treat trailing language tags as labels, not short words in the title.
    tokens = _tokens(os.path.splitext(os.path.basename(name))[0])
    if len(tokens) < 2:
        return set()
    known = set(ALPHA2_TO_ALPHA3) | set(ALPHA3_TO_ALPHA2) | set(SPECIAL_HDBITS_LANGUAGE)
    labels = set()
    for index in range(len(tokens) - 1, 0, -1):
        token = tokens[index]
        if token in {"forced", "sdh", "cc"}:
            continue
        if token == "hi":
            previous = index - 1
            while previous > 0 and tokens[previous] in {"forced", "sdh", "cc"}:
                previous -= 1
            if previous > 0 and (tokens[previous] in known or tokens[previous] in SPELLED_LANGUAGE_NAMES) and tokens[previous] != "hi":
                continue
        if token not in known:
            break
        labels.add(token)
    return labels


def _filename_language_region(name):
    tokens = _tokens(os.path.splitext(os.path.basename(name))[0])
    if len(tokens) < 2:
        return None
    known = set(ALPHA2_TO_ALPHA3) | set(ALPHA3_TO_ALPHA2) | set(SPECIAL_HDBITS_LANGUAGE)
    variants = {"forced", "sdh", "cc"}
    end = len(tokens)
    while end > 1 and tokens[end - 1] in variants:
        end -= 1
    if end > 1 and tokens[end - 1] == "hi":
        previous = end - 2
        while previous > 0 and tokens[previous] in variants:
            previous -= 1
        if previous > 0 and (tokens[previous] in known or tokens[previous] in SPELLED_LANGUAGE_NAMES) and tokens[previous] != "hi":
            end -= 1
            while end > 1 and tokens[end - 1] in variants:
                end -= 1
    if end > 1 and tokens[end - 1] in {"br", "pt"} and tokens[end - 2] in {"pt", "por"}:
        return tokens[end - 1].upper()
    if tokens[end - 1] == "br":
        return "BR"
    return None


def _language_details(language):
    if isinstance(language, dict):
        alpha3 = language.get("alpha3")
        alpha2 = language.get("alpha2")
        country = language.get("country_alpha2") or language.get("country")
    else:
        alpha3 = language
        alpha2 = None
        country = None
    alpha3 = str(alpha3 or "").lower()
    alpha2 = str(alpha2 or "").lower()
    if not alpha3 and alpha2:
        alpha3 = ALPHA2_TO_ALPHA3.get(alpha2, "")
    return alpha3, alpha2, str(country or "").upper()


def _language_hints(language):
    alpha3, alpha2, _country = _language_details(language)
    if not alpha3:
        return set()
    hints = {alpha3}
    mapped_alpha2 = ALPHA3_TO_ALPHA2.get(alpha3)
    if mapped_alpha2:
        hints.add(mapped_alpha2)
    if alpha2:
        hints.add(alpha2)
    hints.update(code for code, (mapped, _country) in SPECIAL_HDBITS_LANGUAGE.items() if mapped == alpha3)
    return hints


def _api_data(payload, context):
    if not isinstance(payload, dict):
        raise ValueError(f"{context} did not return a JSON object")
    if "data" in payload:
        return payload.get("data") or []
    message = payload.get("message") or payload.get("error") or payload.get("status_message")
    status = payload.get("status")
    if message or status not in (None, 0, 1, "0", "1", "ok", "success"):
        detail = message or status or "missing data"
        raise ValueError(f"{context} failed: {detail}")
    return []


def _looks_like_html(body):
    sample = body[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return sample.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))


def _is_rar_archive(body):
    return bool(body) and (
        body.startswith(b"Rar!\x1a\x07\x00")
        or body.startswith(b"Rar!\x1a\x07\x01\x00")
    )
