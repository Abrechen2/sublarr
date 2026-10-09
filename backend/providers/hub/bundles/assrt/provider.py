"""Assrt provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

PROVIDER_ID = "assrt"
BASE_URL = "https://api.assrt.net/v1"
HTTP_TIMEOUT_SECONDS = 15
USER_AGENT = "Sub-Zero/2"
MEANINGLESS_VIDEO_NAMES = {"\u4e0d\u77e5\u9053"}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")

LANGUAGE_CODES = {
    "eng": {
        "alpha3": "eng",
        "alpha2": "en",
        "assrt": "eng",
        "aliases": {"eng", "english"},
    },
    "zho-CN": {
        "alpha3": "zho",
        "alpha2": "zh",
        "country": "CN",
        "assrt": "chs",
        "aliases": {"chs", "chn"},
    },
    "zho-TW": {
        "alpha3": "zho",
        "alpha2": "zh",
        "country": "TW",
        "assrt": "cht",
        "aliases": {"cht", "twn"},
    },
}
ASSRT_TO_LANGUAGE = {}
for _key, _meta in LANGUAGE_CODES.items():
    for _alias in _meta["aliases"]:
        ASSRT_TO_LANGUAGE[_alias] = _meta

_LANGLIST_RE = re.compile(r"^lang(?P<code>\w+)$")
# Further episodes after the first one of a tag: chained ("E01E02", "E01.E02",
# "E01+E02", "E01,E02") or a range ("E01-E03", "E01-03"). A tilde marks a range
# too: NFKD folds the full-width one into "~", and the Japanese wave dash is
# listed as itself. So do an en or em dash, and the "至" and "到" ("to") of
# Chinese names ("S01E01至E05"). A range can also repeat its season at the far
# end ("S01E01-S01E03"), when it is the same season. Only a range mark right
# after the tag may lead a bare number, so "S01E05 - 10 Things" stays one
# episode. The tag's closing guard keeps "-720p" and "-1080p" from reading as
# the end of a range, and a bit depth ("-10-bit") is ruled out by name.
# Each continuation matches one way only: a "0*" before the digits would let
# "E001E001..." split many ways, and a long crafted name would then backtrack
# for minutes.
_RANGE_MARKS = frozenset("-~\N{WAVE DASH}\N{EN DASH}\N{EM DASH}至到")
_RANGE_MARK = "".join(re.escape(mark) for mark in sorted(_RANGE_MARKS))


def _more_episodes(repeat_season):
    continuations = [
        r"[\s._&+,]*e\d{1,3}",
        r"\s*[" + _RANGE_MARK + r"]\s*e\d{1,3}",
        r"[" + _RANGE_MARK + r"]\d{1,3}(?![\s._-]*bit)",
    ]
    if repeat_season:
        continuations.append(r"\s*[" + _RANGE_MARK + r"]\s*s0*(?P=season)[\s._-]*e\d{1,3}")
    return r"(?P<more>(?:" + "|".join(continuations) + r")*)"


_MORE_EPISODE_RE = re.compile(
    r"(?P<separator>[\s._&+," + _RANGE_MARK + r"]*)(?:s\d+[\s._-]*)?e?0*(?P<episode>\d{1,3})", re.I
)
# An Assrt name can run a Chinese title straight into the tag ("剧集S01E02中英").
# \b finds no boundary there, so the guards check for an ASCII letter or digit.
# The season and episode can also sit apart ("S01.E02", "S01 - E02").
_SXXEYY_RE = re.compile(
    r"(?<![a-z0-9])s0*(?P<season>\d{1,2})[\s._-]*e0*(?P<episode>\d{1,3})" + _more_episodes(True) + r"(?![a-z0-9])",
    re.I,
)
_EPISODE_RE = re.compile(
    r"(?<![a-z0-9])(?:episode|ep|e)[\W_]*0*(?P<episode>\d{1,3})" + _more_episodes(False) + r"(?![a-z0-9])",
    re.I,
)
# A season on its own ("S01", "S01.E02", "Season 1"). A contiguous tag gives its
# season only once it parses, so "S01E01v2" names no season at all.
_SEASON_RE = re.compile(
    r"(?<![a-z0-9])s0*(?P<season>\d{1,2})(?![a-z0-9])"
    r"|(?<![a-z0-9])season[\W_]+0*(?P<season_word>\d{1,2})(?![a-z0-9])",
    re.I,
)
# Any SxxEyy-shaped tag, including one the parser cannot read ("S01E01v2",
# "S01.E01HDTV"). A name carrying one is about an episode, not a season pack.
_EPISODE_TAG_RE = re.compile(r"(?<![a-z0-9])s\d+[\s._-]*e\d", re.I)
_PATH_SEPARATOR_RE = re.compile(r"[/\\]")
# A range wider than this gives only its two ends, so one misread number cannot
# spread a release over a whole season.
MAX_EPISODE_RANGE = 100
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


class _AssrtRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to HTTPS Assrt hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = _assrt_host_parts(newurl)
        if parts is None or parts.scheme != "https":
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class AssrtProvider:
    def __init__(self):
        self._quota_by_token = {}

    def search(self, video, languages, config):
        token = _token(config)
        requested = _requested_languages(languages)
        if not requested:
            return []
        video = dict(video or {})
        if video.get("kind") not in {"movie", "episode"}:
            return []
        quota = self._quota(token, config)
        self._sleep(request_delay_seconds(quota))
        payload = self._http_get_json(
            f"{BASE_URL}/sub/search?{urllib.parse.urlencode({'token': token, 'q': build_query(video), 'is_file': 1})}",
            config=config,
        )
        check_api_status(payload)
        results = []
        seen = set()
        for item in ((payload.get("sub") or {}).get("subs") or []):
            if _subtitle_id(item) is None:
                # A row that carries neither "id" nor "fileid" has nothing to
                # download with, so no candidate is built for it at all.
                continue
            for language_code, language_meta in _languages_from_search_item(item):
                requested_language = _match_requested_language(language_meta, requested)
                if not requested_language:
                    continue
                video_name = _video_name(item)
                if not video_name:
                    continue
                if _names_other_episode(video, video_name):
                    continue
                result = self._result(video, item, video_name, language_code, requested_language)
                key = (
                    result["provider_payload"]["subtitle_id"],
                    result["provider_payload"]["language_code"],
                    result["language"]["alpha3"],
                    result["language"].get("country_alpha2"),
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append(result)
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def download(self, provider_payload, language, config):
        del language
        token = _token(config)
        payload = dict(provider_payload or {})
        subtitle_id = payload.get("subtitle_id")
        if not subtitle_id:
            raise ValueError("assrt download requires subtitle_id")
        quota = self._quota(token, config)
        self._sleep(request_delay_seconds(quota))
        detail = self._http_get_json(
            f"{BASE_URL}/sub/detail?{urllib.parse.urlencode({'token': token, 'id': subtitle_id})}",
            config=config,
        )
        check_api_status(detail)
        selected_file = select_download_file(detail, payload)
        download_url = selected_file.get("url") if selected_file else None
        if not download_url:
            raise ValueError(f"assrt detail did not contain a download URL for {subtitle_id}")
        download_url = _https_download_url(download_url)
        self._sleep(request_delay_seconds(quota))
        body = self._http_get_bytes(download_url, config=config)
        # A login, quota or expired-file page can come back as HTTP 200.
        if not body or not body.strip():
            raise ValueError(f"assrt returned an empty file for {subtitle_id}")
        if _looks_like_html(body):
            raise ValueError(f"assrt returned an HTML page instead of a subtitle for {subtitle_id}")
        body = _normalize_line_endings(body)
        filename = selected_file.get("f") if selected_file else None
        return _content_payload(body, _subtitle_extension(filename or payload.get("filename")) or "srt")

    def _quota(self, token, config):
        if token not in self._quota_by_token:
            payload = self._http_get_json(
                f"{BASE_URL}/user/quota?{urllib.parse.urlencode({'token': token})}",
                config=config,
            )
            check_api_status(payload)
            quota = ((payload.get("user") or {}).get("quota"))
            if not isinstance(quota, int) or quota <= 0:
                raise ValueError(f"Cannot get a positive Assrt quota from provider: {payload}")
            self._quota_by_token[token] = quota
        return self._quota_by_token[token]

    def _http_get_json(self, url, timeout=HTTP_TIMEOUT_SECONDS, config=None):
        body = self._http_get_bytes(url, timeout=timeout, config=config)
        return json.loads(body.decode("utf-8"))

    def _http_get_bytes(self, url, timeout=HTTP_TIMEOUT_SECONDS, config=None):
        del config
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": os.environ.get("SZ_USER_AGENT", USER_AGENT),
                "Accept": "application/json,*/*",
            },
        )
        opener = urllib.request.build_opener(_AssrtRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return response.read()

    def _sleep(self, seconds):
        if seconds > 0:
            time.sleep(seconds)

    def _result(self, video, item, video_name, language_code, requested_language):
        matches = derive_matches(video, video_name)
        score = 95 if "episode" in matches or "title" in matches else 80
        subtitle_id = _subtitle_id(item)
        language_id = requested_language["alpha3"]
        if requested_language.get("country"):
            language_id = f"{language_id}-{requested_language['country']}"
        filename = f"assrt.{_slug(video_name)}.{language_code}.{language_id}.{subtitle_id}.srt"
        language = {
            "alpha3": requested_language["alpha3"],
            "alpha2": requested_language["alpha2"],
            "hi": False,
            "forced": False,
        }
        if requested_language.get("country"):
            language["country_alpha2"] = requested_language["country"]
        return {
            "provider": PROVIDER_ID,
            "id": f"assrt-{subtitle_id}-{language_code}-{language_id}",
            "language": language,
            "release_info": video_name,
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": None,
            "display": {
                "source": "assrt",
                "title": video_name,
                "language_code": language_code,
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": subtitle_id,
                "language_code": language_code,
                "filename": filename,
                "season": _safe_int((video or {}).get("season")),
                "episode": _safe_int((video or {}).get("episode")),
            },
        }


def check_api_status(payload):
    if isinstance(payload, dict) and "status" in payload and "errmsg" in payload:
        raise ValueError(f"{payload['errmsg']} ({payload['status']})")


def request_delay_seconds(max_request_per_minute):
    return int(math.ceil(60 / max_request_per_minute))


def build_query(video):
    video = video or {}
    if video.get("kind") == "episode":
        parts = []
        if video.get("series"):
            parts.append(str(video["series"]))
        season = _safe_int(video.get("season"))
        episode = _safe_int(video.get("episode"))
        if season is not None and episode is not None:
            parts.append(f"S{season:02d}E{episode:02d}")
        elif episode is not None:
            parts.append(f"E{episode:02d}")
        return " ".join(parts)
    parts = []
    if video.get("title"):
        parts.append(str(video["title"]))
    if video.get("year"):
        parts.append(str(video["year"]))
    return " ".join(parts)


def derive_matches(video, video_name):
    video = video or {}
    candidate_tokens = set(_tokens(video_name))
    matches = []
    if video.get("kind") == "episode":
        series_tokens = _tokens(video.get("series"))
        if series_tokens and all(token in candidate_tokens for token in series_tokens):
            matches.append("series")
        season = _safe_int(video.get("season"))
        episode = _safe_int(video.get("episode"))
        if season is not None and _text_has_season(video_name, season):
            matches.append("season")
        if season is not None and episode is not None:
            if _text_has_episode(video_name, season, episode):
                matches.append("episode")
            elif "series" in matches and "season" in matches and not _any_episode(video_name):
                matches.append("episode")
    else:
        title_tokens = _tokens(video.get("title"))
        if title_tokens and all(token in candidate_tokens for token in title_tokens):
            matches.append("title")
        year = _safe_int(video.get("year"))
        if year is not None and str(year) in candidate_tokens:
            matches.append("year")
    return matches


def select_download_url(detail, payload):
    selected_file = select_download_file(detail, payload)
    return selected_file.get("url") if selected_file else None


def select_download_file(detail, payload):
    subs = ((detail or {}).get("sub") or {}).get("subs") or []
    if not subs:
        return None
    sub = subs[0]
    files = sub.get("filelist") if isinstance(sub.get("filelist"), list) else []
    if not files:
        return {"url": sub.get("url"), "f": (payload or {}).get("filename")}
    files = [item for item in files if item.get("url")]
    if not files:
        return None
    for episode_files in _episode_file_tiers(files, payload):
        selected = _select_language_file(episode_files, payload)
        if selected:
            return selected
    return None


def _select_language_file(files, payload):
    language_code = str((payload or {}).get("language_code") or "").lower()
    if language_code:
        requested = ASSRT_TO_LANGUAGE.get(language_code, {}).get("assrt", language_code)
        unlabelled = []
        for item in files:
            tags = {
                ASSRT_TO_LANGUAGE[token]["assrt"]
                for token in _tokens(item.get("f")) if token in ASSRT_TO_LANGUAGE
            }
            if requested in tags:
                return item
            if not tags:
                unlabelled.append(item)
        return unlabelled[0] if unlabelled else None
    return files[0]


def _episode_file_tiers(files, payload):
    """The pack members that hold the requested episode, most specific first.

    A member made for that episode alone comes first. A combined subtitle is
    timed for the joined video, so a member listing the episode among others
    ("S01E01E02", or either end of "S01E01-E03") only follows it. A member whose
    range spans the episode comes last, since search offered the subtitle for
    every episode of that range. Each group gets its own language pick.
    """
    target_episode = _safe_int((payload or {}).get("episode"))
    if target_episode is None:
        return [files]
    target_season = _safe_int((payload or {}).get("season"))

    def holds(season_episode):
        season, episode = season_episode
        return episode == target_episode and (target_season is None or season is None or season == target_season)

    alone, listed, spanned = [], [], []
    has_structured_episodes = False
    for item in files:
        file_episodes = _file_episodes(item.get("f"))
        if not file_episodes:
            continue
        has_structured_episodes = True
        if all(map(holds, file_episodes)):
            alone.append(item)
        elif any(map(holds, file_episodes)):
            listed.append(item)
        elif any(map(holds, _file_episodes(item.get("f"), between=True))):
            spanned.append(item)
    if not has_structured_episodes:
        return [files]
    return [tier for tier in (alone, listed, spanned) if tier]


def _requested_languages(languages):
    requested = []
    seen = set()
    for language in languages or []:
        meta = _requested_language_meta(language)
        if not meta:
            continue
        key = (meta["alpha3"], meta.get("country"))
        if key in seen:
            continue
        seen.add(key)
        requested.append(meta)
    return requested


def _requested_language_meta(language):
    if isinstance(language, str):
        alpha3 = language
        country = None
    elif isinstance(language, dict):
        # Assrt has no forced or HI metadata, so it cannot satisfy either variant.
        if language.get("forced") or language.get("hi"):
            return None
        alpha3 = language.get("alpha3") or language.get("code") or language.get("alpha2")
        country = language.get("country") or language.get("country_alpha2") or language.get("region")
    else:
        return None
    alpha3 = str(alpha3 or "").lower()
    # The manifest advertises the declared variant codes "zho-CN"/"zho-TW", so
    # callers may pass them verbatim as the alpha3 value. Split off the region
    # suffix here so they resolve to the correct Simplified/Traditional meta.
    if "-" in alpha3:
        base, _, suffix = alpha3.partition("-")
        if base in {"zh", "zho"}:
            alpha3 = base
            if not country:
                country = suffix
    if alpha3 in {"zh", "zho"}:
        country = str(country or "").upper() or None
        if country == "TW":
            return dict(LANGUAGE_CODES["zho-TW"])
        if country == "CN":
            return dict(LANGUAGE_CODES["zho-CN"])
        return {
            "alpha3": "zho",
            "alpha2": "zh",
            "assrt": "chs",
            "aliases": {"chs", "cht", "chn", "twn"},
        }
    if alpha3 in {"en", "eng"}:
        return dict(LANGUAGE_CODES["eng"])
    return None


def _languages_from_search_item(item):
    # Legacy rows list their languages in "lang.langlist", keyed by "lang<code>".
    # Current rows carry "m_langn" instead, as a single string or a list of the
    # same keys. Read both sources and drop duplicate and non-string entries.
    item = item or {}
    keys = [str(key) for key in (item.get("lang") or {}).get("langlist") or {}]
    m_langn = item.get("m_langn")
    if isinstance(m_langn, str):
        m_langn = [m_langn]
    if isinstance(m_langn, list):
        keys.extend(key for key in m_langn if isinstance(key, str))
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        match = _LANGLIST_RE.fullmatch(key)
        if not match:
            continue
        code = match.group("code").lower()
        if code == "dou":
            # "langdou" (双语) marks a bilingual subtitle. Assrt always pairs the
            # second language with Chinese, so only the Chinese half is reliable
            # here. The other half is not guaranteed to be English (it can be
            # Korean, Japanese, etc.), so we advertise English only when an
            # explicit "langeng" entry is present below.
            yield code, LANGUAGE_CODES["zho-CN"]
            continue
        meta = ASSRT_TO_LANGUAGE.get(code)
        if meta:
            yield code, meta


def _match_requested_language(found_language, requested_languages):
    for requested in requested_languages:
        if requested["alpha3"] != found_language["alpha3"]:
            continue
        if requested.get("country") and requested.get("country") != found_language.get("country"):
            continue
        return requested
    return None


def _video_name(item):
    name = item.get("videoname")
    if isinstance(name, str) and name and name not in MEANINGLESS_VIDEO_NAMES:
        return name
    native = item.get("native_name")
    if isinstance(native, str) and native:
        return native
    if isinstance(native, list):
        for entry in native:
            if isinstance(entry, str) and entry:
                return entry
    # Current rows title the record with "sub_name".
    sub_name = item.get("sub_name")
    if isinstance(sub_name, str) and sub_name:
        return sub_name
    return name if isinstance(name, str) else None


def _subtitle_id(item):
    # Legacy rows carry "id"; current rows carry "fileid" instead. A row with
    # neither has nothing to download with, so search skips it entirely. An
    # empty string is as good as a missing field, so the fallback reads past
    # an empty "id" and an empty "fileid" is no id either.
    item = item or {}
    value = item.get("id")
    if value is None or value == "":
        value = item.get("fileid")
    return None if value is None or value == "" else str(value)


def _token(config):
    token = str((config or {}).get("token") or "").strip()
    if not token:
        raise ValueError("assrt token must be specified")
    return token


def _assrt_host_parts(url):
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
        if parts.port is not None:
            return None
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or not (host == "assrt.net" or host.endswith(".assrt.net")):
        return None
    return parts


def _https_download_url(url):
    # The API documents file links as plain http; the same hosts serve HTTPS.
    parts = _assrt_host_parts(url)
    if parts is None or parts.scheme not in {"http", "https"}:
        raise ValueError("assrt download URL is outside the Assrt file hosts")
    return urllib.parse.urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))


def _names_other_episode(video, video_name):
    season = _safe_int(video.get("season"))
    episode = _safe_int(video.get("episode"))
    if video.get("kind") != "episode" or season is None or episode is None:
        return False
    episodes = _episode_set(video_name)
    return bool(episodes) and (season, episode) not in episodes


def _text_has_episode(text, season, episode):
    return (season, episode) in _episode_set(text)


def _text_has_season(text, season):
    if any(tag_season == season for tag_season, _ in _episode_set(text)):
        return True
    for match in _SEASON_RE.finditer(_normalize(text)):
        if _safe_int(match.group("season") or match.group("season_word")) == season:
            return True
    return False


def _any_episode(text):
    return bool(_EPISODE_TAG_RE.search(_normalize(text)))


def _episode_set(text, between=True):
    """Every (season, episode) pair the SxxEyy tags in a name give.

    A chained tag such as "S01E01E02" gives each episode it lists and no other.
    A range such as "S01E01-E03" or "S01E01-03" gives its first and last
    episode, and with ``between`` the ones between them too, since a release
    or a pack holds each of them.
    """
    episodes = set()
    for match in _SXXEYY_RE.finditer(_normalize(text)):
        season = int(match.group("season"))
        episodes.update((season, episode) for episode in _tag_episodes(match, between))
    return episodes


def _tag_episodes(match, between):
    previous = int(match.group("episode"))
    episodes = {previous}
    for more in _MORE_EPISODE_RE.finditer(match.group("more")):
        episode = int(more.group("episode"))
        if _RANGE_MARKS.isdisjoint(more.group("separator")):
            episodes.add(episode)
        elif episode > previous:
            episodes.add(episode)
            if between and episode - previous < MAX_EPISODE_RANGE:
                episodes.update(range(previous + 1, episode))
        previous = episode
    return episodes


def _file_episodes(filename, between=False):
    """The (season, episode) pairs a pack member names, with season None when it names none.

    The member's own name answers before its folder does: a folder can tag a
    whole range ("Show.S01E01-E10/Show.S01E05.srt"), which would name the same
    episodes for every member inside it.
    """
    path = _normalize(filename).replace("_", " ")
    name = _PATH_SEPARATOR_RE.split(path)[-1]
    for text in (name,) if name == path else (name, path):
        episodes = _episode_set(text, between)
        if episodes:
            return episodes
        match = _EPISODE_RE.search(text)
        if match:
            season = _member_season(text, path)
            return {(season, episode) for episode in _tag_episodes(match, between)}
    return set()


def _member_season(text, path):
    """The season beside a pack member's bare episode tag, or None when it gives none."""
    season = _SEASON_RE.search(text) or _SEASON_RE.search(path)
    if season:
        return _safe_int(season.group("season") or season.group("season_word"))
    # A folder can give it only in a full tag ("Show.S02E05/Show.E05.srt" or
    # "Show.S01E01-E10/Show.E05.srt"), which _SEASON_RE leaves to the tag parser.
    seasons = {tag_season for tag_season, _ in _episode_set(path, between=False)}
    return seasons.pop() if len(seasons) == 1 else None


def _looks_like_html(body):
    sample = body[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return sample.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))


def _normalize_line_endings(body):
    return (body or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _content_payload(body, extension, empty=False):
    data = body or b""
    subtitle_format = (extension or "srt").lstrip(".").lower()
    return {
        "content_b64": base64.b64encode(data).decode("ascii"),
        "content_sha256": hashlib.sha256(data).hexdigest(),
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


def _subtitle_extension(name):
    lower_name = str(name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lower_name.endswith(extension):
            return extension.lstrip(".")
    return None


def _slug(value, max_length=80):
    slug = "-".join(_tokens(value))
    return (slug[:max_length].strip("-") or "subtitle")


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
