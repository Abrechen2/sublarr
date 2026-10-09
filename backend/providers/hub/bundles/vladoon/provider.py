"""Vladoon provider for the Bazarr+ Provider Hub catalog.

Vladoon is a Bulgarian subtitle site with a small JSON search API and ZIP
downloads. The service announced itself as ``vladoon.mooo.com`` when the
upstream provider was written; every request there is now redirected to the
canonical ``vladoon.com`` host, so this provider talks to the canonical
domain directly and skips the redirect hop.
"""

import base64
import hashlib
import io
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile


PROVIDER_ID = "vladoon"
BASE_URL = "https://vladoon.com/subs"
SEARCH_URL = BASE_URL + "/search-subtitles"
DOWNLOAD_URL = BASE_URL + "/download/{item_id}"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
HTTP_TIMEOUT_SECONDS = 20
DOWNLOAD_TIMEOUT_SECONDS = 30
# A search response is a small JSON document; a download is a zip the host
# caps at 32 MiB, so a body above that cap could never be accepted.
MAX_SEARCH_BYTES = 4 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
# The host rejects archives with more members than this guard, so a download
# above it could never be accepted either.
MAX_ARCHIVE_MEMBERS = 5000
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
LANGUAGE_ALPHA3 = "bul"
LANGUAGE_ALPHA2 = "bg"
# The site serves Bulgarian subtitles only and its API carries no
# hearing-impaired or forced flag, so the result language is fixed.
LANGUAGE = {
    "alpha3": LANGUAGE_ALPHA3,
    "alpha2": LANGUAGE_ALPHA2,
    "hi": False,
    "forced": False,
}

_EPISODE_TOKEN_RE = re.compile(r"\b[Ss](\d{1,2})[Ee](\d{1,2})\b")
_EPISODE_ALT_RE = re.compile(r"\b(\d{1,2})x(\d{1,2})\b")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


def _coerce_text(value):
    """Collapse a video-metadata value to a single string.

    Subliminal occasionally serialises multi-value fields (notably
    ``audio_codec`` and ``source``) as a Python ``list`` inside the worker
    payload. Passing a list straight into ``dict.get`` or ``str.lower``
    raises ``TypeError: unhashable type: 'list'`` and crashes search.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        joined = " ".join(str(item) for item in value if item not in (None, ""))
        return joined or None
    return str(value)


def _normalize(text):
    if not text:
        return ""
    # NFKD decomposition strips diacritics on Latin script while leaving
    # non-Latin codepoints intact so they survive normalization.
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _normalize_tokens(text):
    return [token for token in _normalize(_coerce_text(text)).split(" ") if token]


def _release_tokens(text):
    if not text:
        return set()
    # Treat any non-alphanumeric run as a separator. Lowercased for matching.
    return {chunk for chunk in re.split(r"[^A-Za-z0-9]+", str(text).lower()) if chunk}


def _has_token(release_tokens, candidates):
    """True if any synonym in ``candidates`` is present in the release.

    Each entry may be a single token (``"bluray"``) or a multi-word value
    (``"DTS-HD"``, ``"WEB-DL"``); multi-word entries are split into
    alphanumeric chunks and require every chunk to appear in the release.
    """
    for token in candidates:
        if not token:
            continue
        chunks = [chunk for chunk in re.split(r"[^A-Za-z0-9]+", str(token).lower()) if chunk]
        if not chunks:
            continue
        if all(chunk in release_tokens for chunk in chunks):
            return True
    return False


def _multi_token_present(release_tokens, value):
    """True if every alphanumeric chunk of ``value`` is in the release."""
    if not value:
        return False
    chunks = [chunk for chunk in re.split(r"[^A-Za-z0-9]+", str(value).lower()) if chunk]
    if not chunks:
        return False
    return all(chunk in release_tokens for chunk in chunks)


# Release-name match tables. Keys are the values bazarr/subliminal exposes on
# the Video object; the inner list is the set of synonymous tokens searched
# inside a release name. Matching is case-insensitive on tokenized text.
_SOURCE_TOKENS = {
    "Blu-ray": ["bluray", "blueray", "brrip", "bdrip", "bd"],
    "Web": ["web", "webrip", "webdl", "web-dl", "web-dlrip"],
    "WEB-DL": ["webdl", "web-dl", "web"],
    "WEBRip": ["webrip", "web-rip", "web"],
    "HDTV": ["hdtv"],
    "DVD": ["dvd", "dvdrip"],
    "TS": ["ts", "telesync"],
    "CAM": ["cam", "camrip"],
    "HDRip": ["hdrip"],
}
_VIDEO_CODEC_TOKENS = {
    "H.264": ["h264", "x264", "avc"],
    "H.265": ["h265", "x265", "hevc"],
    "DivX": ["divx"],
    "XviD": ["xvid"],
    "AV1": ["av1"],
    "VP9": ["vp9"],
}
_AUDIO_CODEC_TOKENS = {
    "AAC": ["aac"],
    "DTS": ["dts", "dts-x", "dts-es"],
    "DTS-HD": ["dtshd", "dts-hd"],
    "FLAC": ["flac"],
    "MP3": ["mp3"],
    "TrueHD": ["truehd"],
}
# Dolby Digital is AC3 and Dolby Digital Plus is EAC3; the Plus track must
# not be claimed for a plain Dolby Digital request, so the two get ordered
# dedicated handling instead of plain synonym lists.
_AC3_TOKENS = ["ac3", "dd", "dd-ex", "dolby digital"]
_EAC3_TOKENS = ["eac3", "ddp", "dolby digital plus"]
_DOLBY_DIGITAL_PLUS_TOKENS = {"dolby", "digital", "plus"}
_TRAILING_DIGITS_RE = re.compile(r"^(.*[a-z])\d{1,2}$")


def _audio_tokens(release):
    """Release tokens for audio matching, with channel suffixes stripped.

    Release names run the channel count straight into the codec tag
    (``DDP5.1`` tokenizes as ``ddp5``), so audio matching also considers
    tokens with the trailing channel digits stripped. ``DD+`` would
    tokenize as plain ``dd`` (AC3) although it means Dolby Digital Plus, so
    it is rewritten to ``ddp`` before tokenizing.
    """
    text = re.sub(r"(?<![A-Za-z0-9])dd\+", "ddp", str(release or ""), flags=re.IGNORECASE)
    tokens = _release_tokens(text)
    stripped = set()
    for token in tokens:
        match = _TRAILING_DIGITS_RE.match(token)
        if match:
            stripped.add(match.group(1))
    return tokens | stripped


def _audio_codec_matches(audio_codec, release):
    """True when one release name carries the requested audio codec."""
    tokens = _audio_tokens(release)
    if audio_codec == "EAC3":
        return _has_token(tokens, _EAC3_TOKENS)
    if audio_codec == "AC3":
        if _DOLBY_DIGITAL_PLUS_TOKENS <= tokens:
            # Dolby Digital Plus is EAC3, not AC3.
            return False
        return _has_token(tokens, _AC3_TOKENS)
    token_list = _AUDIO_CODEC_TOKENS.get(audio_codec)
    if token_list:
        return _has_token(tokens, token_list)
    return _multi_token_present(tokens, audio_codec)


# Release names abbreviate streaming services (``HMAX``, ``AMZN``), so the
# canonical names the video carries need their token synonyms.
_STREAMING_SERVICE_TOKENS = {
    "HBO Max": ["hmax", "hbo"],
    "Amazon Prime": ["amzn", "amazon", "prime"],
    "Netflix": ["nf", "netflix"],
    "Disney+": ["dsnp", "disney"],
    "Apple TV+": ["atvp", "apple tv"],
    "Hulu": ["hulu"],
    "Peacock": ["pcok", "peacock"],
    "Paramount+": ["pmtp", "paramount"],
    "Crunchyroll": ["crch", "crunchyroll"],
    "HIDIVE": ["hidive"],
}


_ITEM_ID_RE = re.compile(r"^[0-9]+$")


def _valid_item_id(value):
    """True for a positive decimal item id, the only shape the site emits.

    The download URL is built from the id, so anything beyond plain digits
    is rejected rather than percent-encoded into the path.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return bool(_ITEM_ID_RE.match(stripped)) and stripped.strip("0") != ""


def _member_basename(name):
    """Return an archive member's basename.

    Zip members use forward slashes; some producers emit backslashes.
    """
    return str(name).replace("\\", "/").rsplit("/", 1)[-1]


def _is_subtitle_member(name):
    """True when an archive member is a subtitle file worth extracting.

    Mirrors the built-in rule: directories and dot-prefixed members
    (``.DS_Store``, the AppleDouble ``._name.srt`` resource forks macOS zip
    adds) are not subtitles, and only the basename's extension decides.
    """
    base = _member_basename(name)
    if not base or base.startswith("."):
        return False
    return os.path.splitext(base)[1].lower() in SUBTITLE_EXTENSIONS


def _is_forced_member(name):
    """True when an archive member is tagged as a forced subtitle.

    Mirrors the built-in rule, boundary included: only the lowercased
    basename's final segment before the extension counts, so
    ``show.s01e01.forced.srt`` is forced while ``show.forced.1080p.srt``
    is not, and ``nonforced`` as the final segment is skipped too. Forced
    members are only for forced requests, and this provider never
    requests forced.
    """
    base = _member_basename(name).lower()
    return os.path.splitext(base)[0].endswith("forced")


def _episode_tuple(text):
    """Return ``(season, episode)`` from a release name, else ``None``."""
    if not text:
        return None
    match = _EPISODE_TOKEN_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = _EPISODE_ALT_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def _episode_token(video):
    """Return the ``SxxExx`` search token for an episode video."""
    season = (video or {}).get("season")
    episode = (video or {}).get("episode")
    if season is None or episode is None:
        return None
    try:
        return "S%02dE%02d" % (int(season), int(episode))
    except (TypeError, ValueError):
        return None


def _search_query(video):
    """Return the single query string the site is asked to search."""
    video = video or {}
    if video.get("kind") == "episode":
        series = (_coerce_text(video.get("series")) or "").strip()
        token = _episode_token(video)
        if not series or not token:
            return None
        return f"{series} {token}"
    if video.get("kind") == "movie":
        title = (_coerce_text(video.get("title")) or "").strip()
        return title or None
    return None


def _release_names(item):
    releases = item.get("release_names") or []
    if isinstance(releases, str):
        return [releases]
    return [name for name in releases if isinstance(name, str) and name]


def _item_title(item):
    return item.get("original_title") or item.get("title") or ""


def _titles_match(video_text, item):
    """True when the item's title equals the video's title.

    The item's title fields are clean production titles, not release names,
    so the match is exact on the normalized token set (the same semantics
    upstream's guessit title matching applies). A ``Dune`` video must not
    title-match ``Dune: Part Two``; the IMDb id is the discriminator
    between same-title productions.
    """
    video_tokens = set(_normalize_tokens(video_text))
    if not video_tokens:
        return False
    for candidate in (item.get("original_title"), item.get("title")):
        candidate_tokens = set(_normalize_tokens(candidate))
        if candidate_tokens and candidate_tokens == video_tokens:
            return True
    return False


def _matches_movie(item, video):
    """True when a movie result item belongs to the requested movie.

    The site answers a title search with every production carrying that
    title (a ``Dune`` search returns the 2021, 1984 and sequel entries), so
    the IMDb id is the discriminator whenever both sides carry one.
    """
    if (video or {}).get("kind") != "movie":
        return True
    item_type = item.get("type")
    if item_type and item_type != "movie":
        return False
    video_imdb = (video or {}).get("imdb_id")
    item_imdb = item.get("imdb_id")
    if video_imdb and item_imdb:
        return video_imdb == item_imdb
    return True


def _matches_episode(item, video):
    """True when a tv result item covers the requested episode.

    An item covers the episode when its own season/episode fields name it,
    when one of its release names carries the episode token, or when the
    item is a season pack of the requested season.
    """
    if (video or {}).get("kind") != "episode":
        return True
    item_type = item.get("type")
    if item_type and item_type != "tv":
        return False
    series_imdb = (video or {}).get("series_imdb_id")
    item_imdb = item.get("imdb_id")
    if series_imdb and item_imdb and series_imdb != item_imdb:
        return False

    season = (video or {}).get("season")
    episode = (video or {}).get("episode")
    item_season = item.get("season")
    item_episode = item.get("episode")
    if item_season == season and item_episode == episode:
        return True
    for release in _release_names(item):
        if _episode_tuple(release) == (season, episode):
            return True
    if item.get("episode_type") == "season" and item_season == season:
        return True
    return False


def _parse_search_results(body):
    """Parse a search response body into a list of result item dicts.

    Items that are not dicts, or that carry no usable id, are dropped: the
    download URL is built from the id, so an item without one cannot
    produce a usable subtitle.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("Vladoon returned an unreadable search response") from error
    if not isinstance(payload, dict):
        raise ValueError("Vladoon search response is not a JSON object")
    results = payload.get("results")
    if results is None:
        return []
    if not isinstance(results, list):
        raise ValueError("Vladoon search results is not a list")
    # Items that are not dicts, or whose id is not a positive decimal
    # integer, are dropped: the download URL is built from the id, so an
    # item without a plain id cannot produce a safe, usable download.
    return [item for item in results if isinstance(item, dict) and _valid_item_id(item.get("id"))]


def _requested_language(languages):
    """Return the fixed result language when plain Bulgarian is requested.

    The site carries no hearing-impaired or forced variants, so a request
    for one of those variants is not satisfied by a plain result and gets
    no results rather than a mislabelled one.
    """
    for language in languages or []:
        if not isinstance(language, dict):
            continue
        if language.get("hi") or language.get("forced"):
            continue
        alpha3 = language.get("alpha3")
        alpha2 = language.get("alpha2")
        if alpha3 == LANGUAGE_ALPHA3 or alpha2 == LANGUAGE_ALPHA2:
            return dict(LANGUAGE)
    return None


def _derive_matches(video, item):
    """Compute the subliminal-shaped match list for one result item.

    Keys feed bazarr's downstream score calculation
    (``custom_libs/subliminal_patch/score.py``). Each key is added only when
    the item actually carries the matching signal.
    """
    video = video or {}
    matches = []
    kind = video.get("kind")
    releases = _release_names(item)

    if kind == "movie":
        if _titles_match(video.get("title"), item):
            matches.append("title")
        year = video.get("year")
        if year and any(str(year) in _release_tokens(release) for release in releases):
            matches.append("year")
        if video.get("imdb_id") and item.get("imdb_id") == video.get("imdb_id"):
            matches.append("imdb_id")
    elif kind == "episode":
        if _titles_match(video.get("series"), item):
            matches.append("series")
        try:
            season = int(video.get("season"))
            episode = int(video.get("episode"))
        except (TypeError, ValueError):
            season = episode = None
        if season is not None:
            for release in releases:
                tag = _episode_tuple(release)
                if tag is not None and tag[0] == season:
                    matches.append("season")
                    break
            if item.get("season") == season:
                matches.append("season")
        if season is not None and episode is not None:
            for release in releases:
                if _episode_tuple(release) == (season, episode):
                    matches.append("episode")
                    break
            if item.get("season") == season and item.get("episode") == episode:
                matches.append("episode")
        if video.get("series_imdb_id") and item.get("imdb_id") == video.get("series_imdb_id"):
            # The item's id is the series-level identity: emit the
            # series_imdb_id key, which the score contract credits with
            # series and year, not imdb_id, which claims season and
            # episode equivalence this comparison never established.
            matches.append("series_imdb_id")
        year = video.get("year")
        if year and any(str(year) in _release_tokens(release) for release in releases):
            matches.append("year")

    matches.extend(_release_attribute_matches(video, item, releases))

    # One entry per key, in a stable order.
    return list(dict.fromkeys(matches))


_ATTRIBUTE_KEYS = (
    "source",
    "resolution",
    "video_codec",
    "audio_codec",
    "release_group",
    "streaming_service",
    "edition",
)
# The release identity keys: these outweigh the generic attribute keys
# when ranking archive members, because a member that disagrees with the
# video's source or release group is mistimed no matter how many generic
# tags its filename spells out.
_IDENTITY_ATTRIBUTE_KEYS = ("source", "streaming_service", "release_group")


def _tag_synonym_chunks(*tables):
    """The accent-folded chunks of every synonym in the given tag tables.

    A dict table contributes its keys and every synonym in its value
    lists; a list table contributes its entries. The compound-boundary
    and body-token sets below derive from this inventory, so both stay
    in sync with the tag tables.
    """
    for table in tables:
        synonyms = list(table)
        if isinstance(table, dict):
            synonyms.extend(token for tokens in table.values() for token in tokens)
        for synonym in synonyms:
            yield _normalize_tokens(synonym)


# A hyphen segment that continues a compound source or audio tag
# (``WEB-DL``, ``DTS-HD``, ``Dolby-Digital-Plus``) belongs to the release
# body, not to the trailing release group. Every adjacent pair inside a
# multi-chunk synonym is a boundary, so the group span never starts
# inside a compound tag and no pair of one is left mid-name.
_COMPOUND_TAG_BOUNDARIES = {
    pair
    for chunks in _tag_synonym_chunks(
        _SOURCE_TOKENS,
        _VIDEO_CODEC_TOKENS,
        _AUDIO_CODEC_TOKENS,
        _STREAMING_SERVICE_TOKENS,
        _AC3_TOKENS,
        _EAC3_TOKENS,
    )
    for pair in zip(chunks, chunks[1:])
}
# A hyphen segment that carries a codec, audio or streaming token, or a
# long-form source token (``BluRay``, ``WEBRip``, ``HDTV``), names the
# release or its technical profile, so it is body content and the group
# span stops before it. The short, ambiguous source tokens (``BD``,
# ``WEB``, ``TS``, ``CAM``, ``DVD``) are deliberately absent: a trailing
# hyphen segment carrying one is more plausibly the release group (a
# release group can genuinely be named ``WEB``), and its source claim is
# suppressed because the whole hyphen group span is dropped from source
# matching. In the dot and space walks those tokens are body content
# instead: no release name run on dots or spaces carries one as its
# group.
_AMBIGUOUS_SOURCE_TOKENS = frozenset({"bd", "web", "ts", "cam", "dvd"})
# Release-profile modifiers (``Atmos``, ``REMUX``, ``Hybrid``) and the
# subtitle track annotations that name the track: a hyphen segment
# carrying one names the release's profile, so the group behind it
# still fires.
_BODY_MODIFIER_TOKENS = frozenset(
    {
        "atmos",
        "remux",
        "hybrid",
        "proper",
        "repack",
        "extended",
        "remastered",
        "unrated",
        "dual",
        "audio",
        "internal",
        "limited",
        "hdr",
        "hdr10",
        "10bit",
        "dv",
        "dovi",
        "sdr",
        "uhd",
        "ma",
    }
)
_BODY_TAG_TOKENS = {
    chunk
    for chunks in _tag_synonym_chunks(
        _VIDEO_CODEC_TOKENS,
        _AUDIO_CODEC_TOKENS,
        _STREAMING_SERVICE_TOKENS,
        _AC3_TOKENS,
        _EAC3_TOKENS,
    )
    for chunk in chunks
} | {
    chunk
    for chunks in _tag_synonym_chunks(_SOURCE_TOKENS)
    for chunk in chunks
    if chunk not in _AMBIGUOUS_SOURCE_TOKENS
} | set(_DOLBY_DIGITAL_PLUS_TOKENS) | _BODY_MODIFIER_TOKENS
# Resolutions are matched by shape: three or four digits plus a
# progressive or interlaced letter (``720p``, ``1080p``, ``2160p``).
_RESOLUTION_TOKEN_RE = re.compile(r"\d{3,4}[pi]")


def _is_year_chunk(chunk):
    """True for a four-digit year chunk, which is never zero-padded."""
    return len(chunk) == 4 and chunk.isdigit() and chunk[0] != "0"


def _is_body_chunk(chunk, dot_or_space=False):
    """True when a single chunk is release-body content.

    A codec, audio, streaming, profile-modifier or long-form source
    token, with channel digits stripped (``AAC2.0``, ``DDP5.1``,
    ``DTS-X.7.1``), or a resolution names the release or its technical
    profile; a short ambiguous source token is one only in a walk over
    dot or space segments.
    """
    if chunk in _BODY_TAG_TOKENS or (
        dot_or_space and chunk in _AMBIGUOUS_SOURCE_TOKENS
    ):
        return True
    stripped = _TRAILING_DIGITS_RE.match(chunk)
    if stripped and stripped.group(1) in _BODY_TAG_TOKENS:
        return True
    return _RESOLUTION_TOKEN_RE.fullmatch(chunk) is not None


def _chunks_body_signal(chunks, dot_or_space=False):
    """The release-body signal pre-normalized chunks carry.

    Returns ``"tags"`` when the chunks carry a codec, audio,
    streaming, profile-modifier or long-form source token, with
    channel digits stripped (``AAC2.0``, ``DDP5.1``, ``DTS-X.7.1``), a
    resolution, or, in a walk over dot or space segments, a short
    ambiguous source token: those name the release or its technical
    profile. Returns ``"year"`` when they only carry a four-digit year,
    which names the release without evidencing a group behind it.
    Returns ``None`` when they carry no body signal; a year whose only
    company is a short source token is a counter on the group instead
    (``BD.1234``, ``BD.0001``).
    """
    for chunk in chunks:
        if _is_body_chunk(chunk, dot_or_space):
            return "tags"
    non_year = [chunk for chunk in chunks if not _is_year_chunk(chunk)]
    if non_year and all(chunk in _AMBIGUOUS_SOURCE_TOKENS for chunk in non_year):
        return None
    if any(_is_year_chunk(chunk) for chunk in chunks):
        return "year"
    return None


def _segment_body_signal(segment, dot_or_space=False):
    """The release-body signal a segment carries, for the group walk."""
    return _chunks_body_signal(_normalize_tokens(segment), dot_or_space)


def _segment_is_annotated_group(segment, dot_or_space=False):
    """True when a segment is a group name with trailing annotations.

    A segment whose chunks lead with group content and trail only with
    annotation chunks (``CM.REPACK``, ``CM.Atmos.HI``, ``CM.REPACK.CD1``)
    names a release group with annotations joined behind it, not
    release body content: the annotations name the track behind the
    group. A segment whose body chunks lead (``BluRay.x264``,
    ``REMUX``) is body content, and an annotation that only follows
    them in a longer technical segment stays body content too.
    """
    chunks = _normalize_tokens(segment)
    index = 0
    while index < len(chunks) and not _is_body_chunk(chunks[index], dot_or_space):
        index += 1
    if index == 0 or index == len(chunks):
        return False
    return all(_is_group_tail_chunk(chunk) for chunk in chunks[index:])


def _tokens_without_title(chunks, title_chunks):
    """Chunks without the title's own consecutive token occurrence.

    A title that does not appear as the full sequence falls back to
    dropping the leading run of its tokens.
    """
    if not title_chunks:
        return chunks
    for start in range(len(chunks) - len(title_chunks) + 1):
        if chunks[start : start + len(title_chunks)] == title_chunks:
            return chunks[:start] + chunks[start + len(title_chunks) :]
    title_tokens = set(title_chunks)
    index = 0
    while index < len(chunks) and chunks[index] in title_tokens:
        index += 1
    return chunks[index:]


def _is_channel_fragment(parts, index):
    """True when the segment at index is a split channel count.

    A name run on dots or spaces can split the channel count off its
    audio tag (a dotted ``TrueHD.7.1`` becomes ``TrueHD``, ``7`` and
    ``1``; a space-joined ``5.1`` is one segment): a segment that is
    only short digit runs is that half when the nearest segment behind
    it that is not itself only short digits carries a technical tag of
    the release (``truehd``, ``dts-hd``, ``ma``, a codec). Behind a
    release group (``...SPARKS.1``) the same digits are a disc number
    and stay group tail content.
    """
    if not _is_short_digit_run(parts[index]):
        return False
    for position in range(index - 1, max(index - 5, -1), -1):
        previous = _normalize_tokens(parts[position])
        if previous and all(
            len(chunk) <= 2 and chunk.isdigit() for chunk in previous
        ):
            # A chain of channel digits (the ``7`` of ``TrueHD.7.1``)
            # belongs to the same split tag; a chain longer than a
            # channel count is not one, and capping the scan bounds
            # the walk on an uploader's pathological digit-run name.
            continue
        return any(
            chunk in _BODY_TAG_TOKENS
            or _RESOLUTION_TOKEN_RE.fullmatch(chunk)
            or (
                (stripped := _TRAILING_DIGITS_RE.match(chunk)) is not None
                and stripped.group(1) in _BODY_TAG_TOKENS
            )
            for chunk in previous
        )
    return False


def _is_short_digit_run(segment):
    """True when a segment is only one- or two-digit chunks."""
    chunks = _normalize_tokens(segment)
    return bool(chunks) and all(
        len(chunk) <= 2 and chunk.isdigit() for chunk in chunks
    )


def _release_components(release):
    """The path components of a release name or archive member."""
    return [part for part in str(release or "").replace("\\", "/").split("/") if part]


def _strip_subtitle_extension(text):
    """Return text without a trailing subtitle file extension."""
    lowered = str(text or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return str(text)[: len(text) - len(extension)]
    return str(text)


_LANGUAGE_ANNOTATION_BRACKET_RE = re.compile(
    rf"\[(?:{LANGUAGE_ALPHA2}|{LANGUAGE_ALPHA3})\]$", re.IGNORECASE
)
_LANGUAGE_ANNOTATION_HYPHEN_RE = re.compile(
    rf"-(?:{LANGUAGE_ALPHA2}|{LANGUAGE_ALPHA3})$", re.IGNORECASE
)


def _component_stem(component):
    """A component without its subtitle extension and language annotation.

    A member can trail with the site's language marker before or inside
    the extension (``...-CM.bg.srt``, ``...-CM[BG].srt``,
    ``...-CM-BG.srt``, and a bare ``Movie.2024-BG.srt``); the marker is
    not release content, so the extension and a trailing marker of the
    site's own language are dropped before tags are compared.
    """
    stem = _strip_subtitle_extension(component)
    stem = _LANGUAGE_ANNOTATION_BRACKET_RE.sub("", stem)
    segments = stem.split(".")
    if len(segments) > 1 and _normalize_tokens(segments[-1]) in (
        [LANGUAGE_ALPHA2],
        [LANGUAGE_ALPHA3],
    ):
        stem = ".".join(segments[:-1])
    return _LANGUAGE_ANNOTATION_HYPHEN_RE.sub("", stem).strip(" ._-")


def _title_pairs(title):
    """The adjacent token pairs of the production title, accent-folded."""
    chunks = _normalize_tokens(title)
    return set(zip(chunks, chunks[1:]))


def _trailing_annotation_start(parts):
    """The index where a component's trailing annotation segments start.

    The segments at a component's end whose chunks are only annotation
    chunks (``REPACK``, ``PROPER``, ``REPACK.HI``, a run of them)
    annotate the release behind its group, so they are span content
    rather than body evidence. Bare digits are not: they are disc
    numbers or the split channel counts a technical tag owns
    (``TrueHD.7.1``). Returns ``len(parts)`` when no trailing segment
    is one.
    """
    start = len(parts)
    while start > 0:
        chunks = _normalize_tokens(parts[start - 1])
        if not chunks or not all(
            _is_group_tail_chunk(chunk) and not chunk.isdigit()
            for chunk in chunks
        ):
            break
        start -= 1
    return start


def _trailing_group_parts(parts, title_pairs, title_chunks, dot_or_space=False):
    """The trailing segments of a component that form its group, with
    whether the span was stopped by release tags.

    The group grows from the end, segment by segment, while the next
    segment carries no release-body signal: a segment that continues a
    compound source or audio tag (``WEB-DL``, ``DTS-HD``,
    ``Dolby-Digital-Plus``), that continues the production title
    (``Spider-Man.2024.BluRay.x264-CM`` keeps its ``CM`` group and its
    ``BluRay`` source), or that carries a tag or year signal is body
    content, except a group name with annotations joined behind it
    (``...x264-CM.REPACK``) and a trailing segment that is only
    profile-modifier chunks (``...x264-CM-REPACK``,
    ``...x264.CM.REPACK``), which are group content: the annotations
    name the track behind the group. A multi-segment group stays whole
    (``...x264-BD-FOO-BAR``). The component's first segment is always
    body content. Returns the span and whether it was stopped by
    release tags, a compound tag or a tag signal, rather than by the
    title, a year alone, or running out of segments.
    """
    start = len(parts)
    stopped_by_tags = False
    annotation_start = _trailing_annotation_start(parts)
    while start > 1:
        candidate = start - 1
        before = _normalize_tokens(parts[candidate - 1])
        opening = _normalize_tokens(parts[candidate])
        if not opening:
            break
        if before:
            pair = (before[-1], opening[0])
            if pair in _COMPOUND_TAG_BOUNDARIES:
                stopped_by_tags = True
                break
            if pair in title_pairs:
                break
        if candidate >= annotation_start:
            # A trailing segment that is only profile-modifier chunks
            # annotates the release behind the group, so it is span
            # content, not body evidence.
            start = candidate
            continue
        if dot_or_space and _is_channel_fragment(parts, candidate):
            stopped_by_tags = True
            break
        signal = _segment_body_signal(parts[candidate], dot_or_space)
        if signal is not None:
            if signal == "tags" and _segment_is_annotated_group(
                parts[candidate], dot_or_space
            ):
                start = candidate
                continue
            if signal == "tags":
                stopped_by_tags = True
            break
        start = candidate
    if start == 1 and not stopped_by_tags:
        # The walk ran out of segments: the first segment is body
        # content by rule, and its own tags, behind the production
        # title's occurrence, are the evidence that the span trails a
        # release (``Movie.2024.BluRay.x264 CM.srt``). A bare title,
        # even one whose word is itself a tag chunk (``Ray``, a
        # Blu-ray chunk), or a title with a year alone
        # (``Movie.Bulgarian.srt``) is not.
        stopped_by_tags = (
            _chunks_body_signal(
                _tokens_without_title(_normalize_tokens(parts[0]), title_chunks),
                dot_or_space,
            )
            == "tags"
        )
    return parts[start:], stopped_by_tags


def _release_body_and_group(component, title):
    """The component's release body, its trailing group segments and
    the separator that joins them.

    The group is the stem's trailing hyphen segments; a name that
    separates its tags with dots or spaces instead (the site's own
    ``Dune.Part.Two.2024.1080p.HDTS.CLEAN.X264.COLLECTIVE``,
    ``Devil In Dune (2021) HDRip XviD WKD``) carries its group as
    trailing dot or space segments, so the same walk runs over those
    segments when no hyphen span exists. All walks stop before compound
    tags, the production title and technical-tag segments, never take
    the component's first segment, and treat the short ambiguous
    source tokens as group content only in the hyphen walk: a name run
    on dots or spaces never carries one as its group, so its trailing
    ``WEB`` or ``BD`` stays a source claim. A dot or space span only
    names a group when release tags stopped the walk, not the title or
    a year alone: a span that trails nothing but a bare production name
    (``Movie.Bulgarian.srt``, ``Movie.2024.Bulgarian.srt``) or a
    title's own words (``Devil.In.Dune.srt``) is not a group.
    """
    stem = _component_stem(component)
    title_chunks = _normalize_tokens(title)
    title_pairs = _title_pairs(title)
    parts = stem.split("-")
    group, _ = _trailing_group_parts(parts, title_pairs, title_chunks)
    if group and not all(
        _is_group_tail_chunk(chunk)
        for part in group
        for chunk in _normalize_tokens(part)
    ):
        # A hyphen span that is only disc numbers or language markers
        # trails a group named by another separator
        # (``Movie.2024.BluRay.x264.CM-1.srt``) or no group at all
        # (``...x264-1.srt``); it is not the group itself.
        return "-".join(parts[: len(parts) - len(group)]), group, "-"
    for separator in (".", " "):
        parts = stem.split(separator)
        group, stopped_by_tags = _trailing_group_parts(
            parts, title_pairs, title_chunks, dot_or_space=True
        )
        if not group or not stopped_by_tags:
            continue
        if separator == "." and any(
            " " in part for part in parts[len(parts) - len(group) - 1 :]
        ):
            # A dot split of a name run on spaces shreds its tags
            # across segments, whether into the group or into the
            # segment that stopped the walk; the space walk behind it
            # sees them whole.
            continue
        return (
            separator.join(parts[: len(parts) - len(group)]),
            group,
            separator,
        )
    return stem, [], ""


def _is_group_tail_chunk(chunk):
    """True for a chunk that trails a release group without naming it.

    Multi-part releases number their discs after the group
    (``...-CM-1``, ``...-DEiTY.CD1``), a member can carry the site's
    language marker behind the group (``...-CM-BG``), a subtitle
    track can carry its hearing annotation (``...-CM-HI``), and a
    release can carry its profile behind the group
    (``...-CM-REPACK``); none of them is part of the group's name.
    """
    return (
        chunk in _BODY_MODIFIER_TOKENS
        or chunk.isdigit()
        or re.fullmatch(r"cd\d+", chunk) is not None
        or chunk in (LANGUAGE_ALPHA2, LANGUAGE_ALPHA3)
        or chunk in ("hi", "sdh")
    )


def _release_group_matches(component, requested_group, title):
    """True when a component's trailing release-group span is the group.

    The group span is derived with ``_release_body_and_group``: the
    trailing hyphen segments of the stem, or its trailing dot or space
    segments when the name separates its tags with dots or spaces,
    stopped before compound
    tags, the production title and technical-tag segments. The
    requested group must be the span's leading, ordered, accent-folded
    token sequence. Chunks dot-joined behind it inside its own segment
    annotate the group rather than name it (``...-CM.HI``,
    ``...-CM.Bulgarian``, ``...-EVO[TGx]``, ``...-DEiTY.CD1``), so they
    are accepted; every later hyphen segment must name nothing (a disc
    number, the language code or the release's profile, ``...-CM-BG``,
    ``...-CM-REPACK``), while the segments of
    a dot or space span only annotate the group behind its name. A
    requested group
    token therefore never fires from a source or codec position
    (``WEB-DL`` carries no ``DL`` group), from a title, from a name
    without a group span, from a longer group it only prefixes
    (``CM`` does not match ``CM-OTHER``), or across a path boundary; a
    hyphenated group (``FOO-BAR``) still matches its full trailing span.
    """
    requested = _normalize_tokens(requested_group)
    if not requested:
        return False
    _, segments, separator = _release_body_and_group(component, title)
    if not segments:
        return False
    flat = [
        chunk for segment in segments for chunk in _normalize_tokens(segment)
    ]
    if flat[: len(requested)] != requested:
        return False
    index = len(requested)
    for position, segment in enumerate(segments):
        chunks = _normalize_tokens(segment)
        if index == 0:
            # The group is fully named: every later hyphen segment must
            # trail it without naming anything, while segments joined
            # by the group's own dot or space separator only annotate
            # the group behind its name.
            if separator == "-" and not all(
                _is_group_tail_chunk(chunk) for chunk in chunks
            ):
                return False
            continue
        if index >= len(chunks):
            index -= len(chunks)
            continue
        # The requested group ends inside this segment: the chunks
        # dot-joined behind it here annotate the group rather than
        # name it, so only later segments are held to the strict rule.
        index = 0
    return index == 0


def _source_tokens(release, title):
    """Release tokens for source matching, without the title occurrence.

    Release names lead with the production title, sometimes behind a
    leading annotation (``[BG].The.Web.2024.1080p.BluRay``), and a title
    word can collide with a source synonym (``The.Web.2024.WEB-DL`` is
    a web release of a production titled ``The Web``; its second ``web``
    is a source claim, the title's is not). So source matching runs on
    the release with its subtitle extension, language annotation and
    trailing release-group span dropped, without the title's own
    consecutive token occurrence, wherever it appears: a title word
    outside that occurrence still claims its source. A title that does
    not appear as the full sequence falls back to dropping the leading
    run of its tokens. Both sides use the accent-folded normalizer, so
    an accented title still excludes its plain release spelling
    (``Café Web`` / ``Cafe.Web``).
    """
    title_chunks = _normalize_tokens(title)
    body, group, _ = _release_body_and_group(release, title)
    return set(_tokens_without_title(_normalize_tokens(body), title_chunks))


# Every source synonym chunk, the short ambiguous ones included: a
# component carrying one names a release source, which is a release tag
# even where it is too ambiguous to end a group span.
_RELEASE_TAG_TOKENS = _BODY_TAG_TOKENS | {
    chunk
    for chunks in _tag_synonym_chunks(_SOURCE_TOKENS)
    for chunk in chunks
}


def _component_carries_release_tags(component, title):
    """True when a path component names release tags of its own.

    A component with a release-group span, or with a tag token, a year
    or a resolution behind the production title, describes a release
    variant. A bare production name (``Movie.bg.srt``) carries none, and
    the release it belongs to is named by an outer component, its
    directory.
    """
    body, group, _ = _release_body_and_group(component, title)
    if group:
        return True
    # A year alone does not carry release identity: a bare basename
    # (``Movie.2024.bg.srt``) belongs to the release its directory
    # names, and only a tag token, its channel digits stripped as the
    # audio matcher strips them (``DDP5.1``), or a resolution names a
    # variant.
    return any(
        chunk in _RELEASE_TAG_TOKENS
        or _RESOLUTION_TOKEN_RE.fullmatch(chunk)
        or (
            (stripped := _TRAILING_DIGITS_RE.match(chunk)) is not None
            and stripped.group(1) in _RELEASE_TAG_TOKENS
        )
        for chunk in _source_tokens(component, title)
    )


def _component_attribute_matches(video, component, title):
    """The attribute keys a single path component's name matches."""
    matched = set()
    tokens = _release_tokens(component)
    source = _coerce_text(video.get("source"))
    if source:
        source_tokens = _source_tokens(component, title)
        token_list = _SOURCE_TOKENS.get(source)
        if (token_list and _has_token(source_tokens, token_list)) or (
            token_list is None and _multi_token_present(source_tokens, source)
        ):
            matched.add("source")
    resolution = _coerce_text(video.get("resolution"))
    if resolution and str(resolution).lower() in tokens:
        matched.add("resolution")
    video_codec = _coerce_text(video.get("video_codec"))
    if video_codec:
        token_list = _VIDEO_CODEC_TOKENS.get(video_codec)
        if (token_list and _has_token(tokens, token_list)) or (
            token_list is None and _multi_token_present(tokens, video_codec)
        ):
            matched.add("video_codec")
    audio_codec = _coerce_text(video.get("audio_codec"))
    if audio_codec and _audio_codec_matches(audio_codec, component):
        matched.add("audio_codec")
    release_group = _coerce_text(video.get("release_group"))
    if release_group and _release_group_matches(component, release_group, title):
        matched.add("release_group")
    streaming_service = _coerce_text(video.get("streaming_service"))
    if streaming_service:
        token_list = _STREAMING_SERVICE_TOKENS.get(streaming_service)
        if (token_list and _has_token(tokens, token_list)) or (
            token_list is None and _multi_token_present(tokens, streaming_service)
        ):
            matched.add("streaming_service")
    edition = _coerce_text(video.get("edition"))
    if edition and _multi_token_present(tokens, edition):
        matched.add("edition")
    return matched


def _release_attribute_matches(video, item, releases):
    """Release-level match keys, evaluated on the release's own name.

    The upstream provider evaluates each release name independently and
    unions the resulting match keys. Pooling every release's tokens into
    one set would manufacture matches: a video release group ``FOO-BAR``
    must not match one release ending ``-FOO`` and another ending
    ``-BAR``. A release name (or archive member path) is described by
    its innermost component that carries release tags of its own or that
    already matches the video: the member's basename when it names a
    variant, even one only the video's own free-form attributes name
    (an ``AV1`` codec), else the release directory behind a bare
    basename. Scoring every component would let a directory's tags
    override the variant the member's own basename names (a WEB-DL
    resync inside a Blu-ray release's directory), and pooling
    components would leak a title occurrence, group segment or source
    tokens across the path boundary. The keys are returned in a fixed
    order.
    """
    matched = set()
    title = _item_title(item)
    for release in releases:
        components = _release_components(release)
        for component in reversed(components):
            # The innermost component that carries release tags of its
            # own, or that the video's own attributes already match,
            # describes the release; a component that does neither
            # names no variant of it.
            component_matches = _component_attribute_matches(
                video, component, title
            )
            if component_matches or _component_carries_release_tags(
                component, title
            ):
                matched.update(component_matches)
                break
    return [key for key in _ATTRIBUTE_KEYS if key in matched]


def _select_movie_member(names, payload):
    """Pick the movie member whose release best matches the video.

    A movie archive carries one member per release variant, and the
    candidate's attribute matches are the union over the item's
    releases, so the pick must deliver the variant that carries the
    matched attributes; archive order would deliver an arbitrary variant,
    possibly mistimed for the video's release. Release identity (the
    source, the streaming service and the release group) outweighs the
    generic attributes (the resolution, the codecs, the edition), so a
    fuller filename on a wrong-source variant does not outrank the
    variant that agrees with the video's release. Each member is scored
    on its innermost path component that carries release tags of its
    own, so a per-release directory carries the variant's tags over a
    plain filename without overriding a basename that names its own
    variant. Ties keep archive order, and a payload without release
    attributes (an older search's, or a video that carries none) keeps
    the first-member behavior.
    """
    payload = payload or {}
    video = payload.get("video") or {}
    if not video:
        return names[0]
    item = {"title": payload.get("title")}
    best_name = names[0]
    best_rank = (-1, -1)
    for name in names:
        matched = _release_attribute_matches(video, item, [name])
        rank = (
            len([key for key in matched if key in _IDENTITY_ATTRIBUTE_KEYS]),
            len(matched),
        )
        if rank > best_rank:
            best_name = name
            best_rank = rank
    return best_name


def _compute_score(video, matches):
    """Heuristic score in [60, 100] from the derived match list.

    - 100: movie with a matching IMDb id, or title and year both matching.
    - 95: episode item naming the season and episode.
    - 90: movie title match, or an episode item covering the season.
    - 85: episode series match only.
    - 60: nothing beyond the site's own search relevance.
    """
    kind = (video or {}).get("kind")
    if kind == "movie":
        if "imdb_id" in matches or ("title" in matches and "year" in matches):
            return 100
        if "title" in matches:
            return 90
        return 60
    if kind == "episode":
        if "episode" in matches:
            return 95
        if "season" in matches:
            return 90
        if "series" in matches:
            return 85
        return 60
    return 60


def _result_filename(item):
    """Return the result filename from the item's first release name."""
    releases = _release_names(item)
    if releases:
        name = releases[0].strip()
        if name.lower().endswith(SUBTITLE_EXTENSIONS):
            return name
        return f"{name}.srt"
    return f"vladoon.{item.get('id')}.{LANGUAGE_ALPHA2}.srt"


def _sleep(config):
    delay = (config or {}).get("request_delay_ms")
    if not delay:
        return
    time.sleep(min(float(delay), 5000.0) / 1000.0)


class VladoonProvider:
    def search(self, video, languages, config):
        video = video or {}
        if _requested_language(languages) is None:
            return []
        query = _search_query(video)
        if not query:
            return []

        url = SEARCH_URL + "?" + urllib.parse.urlencode({"q": query})
        _sleep(config)
        body = self._http_get(url, timeout=HTTP_TIMEOUT_SECONDS)
        items = _parse_search_results(body)

        results = []
        for item in items:
            if not _matches_movie(item, video):
                continue
            if not _matches_episode(item, video):
                continue
            item_id = str(item.get("id"))
            download_url = DOWNLOAD_URL.format(item_id=item_id)
            releases = _release_names(item)
            release_info = "\n".join(releases) or _item_title(item)
            matches = _derive_matches(video, item)
            score = _compute_score(video, matches)
            # The payload carries the requested episode, not the item's: an
            # item can be a season pack covering the episode, and the
            # download must still pick the member for the requested episode.
            payload = {
                "provider": PROVIDER_ID,
                "schema": 1,
                "item_id": item_id,
                "kind": video.get("kind"),
            }
            if video.get("kind") == "episode":
                payload["season"] = video.get("season")
                payload["episode"] = video.get("episode")
            else:
                # The movie member pick ranks the archive's release
                # variants by the video's release attributes, so the
                # payload carries them, plus the item's title whose
                # tokens are excluded from source matching, for the
                # separate download call.
                attributes = {
                    key: _coerce_text(video.get(key)) for key in _ATTRIBUTE_KEYS
                }
                attributes = {key: value for key, value in attributes.items() if value}
                if attributes:
                    payload["video"] = attributes
                payload["title"] = _item_title(item)
            results.append(
                {
                    "provider": PROVIDER_ID,
                    "id": f"{PROVIDER_ID}-{item_id}",
                    "language": dict(LANGUAGE),
                    "release_info": release_info,
                    "filename": _result_filename(item),
                    "matches": matches,
                    "score": score,
                    "score_without_hash": score,
                    "score_out_of": 100,
                    "hash_verifiable": False,
                    "hearing_impaired_verifiable": False,
                    "hearing_impaired": False,
                    "page_link": download_url,
                    "display": {
                        "source": PROVIDER_ID,
                        "title": _item_title(item),
                        "uploader": item.get("uploaded_by"),
                        "download_url": download_url,
                    },
                    "provider_payload": payload,
                }
            )
        return results

    def download(self, provider_payload, language, config):
        del language  # the site serves one language only
        payload = dict(provider_payload or {})
        if payload.get("provider") not in (None, PROVIDER_ID):
            raise ValueError("Vladoon download payload belongs to another provider")
        item_id = payload.get("item_id")
        if not _valid_item_id(item_id):
            raise ValueError("Vladoon download requires a numeric item_id")
        # The URL is built from the item id alone so a tampered payload
        # cannot point the worker at a foreign host.
        url = DOWNLOAD_URL.format(item_id=str(item_id).strip())

        _sleep(config)
        body = self._http_get(
            url, timeout=DOWNLOAD_TIMEOUT_SECONDS, max_bytes=MAX_DOWNLOAD_BYTES
        )
        if not zipfile.is_zipfile(io.BytesIO(body)):
            raise ValueError(f"Vladoon download {url} is not an archive")

        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            member_names = bundle.namelist()
            if len(member_names) > MAX_ARCHIVE_MEMBERS:
                # Mirror the host's member-count guard: an archive above it
                # would be rejected host-side anyway, so fail early with a
                # clear error instead of building a payload for nothing.
                raise ValueError(
                    f"Vladoon download {url} carries too many members"
                )
            names = [name for name in member_names if _is_subtitle_member(name)]
        if not names:
            raise ValueError(f"Vladoon download {url} carries no subtitle member")

        if payload.get("kind") == "episode":
            season = payload.get("season")
            episode = payload.get("episode")
            try:
                wanted = (int(season), int(episode))
            except (TypeError, ValueError):
                wanted = None
            # Forced-tagged members are only for forced requests, and this
            # provider never requests forced, so a normal episode request
            # must not receive them. Upstream's multi-member path filters
            # them, but its single-member shortcut (and the host's copy of
            # it) would still serve a forced-only archive, so the worker
            # rejects a forced-only archive itself.
            eligible = [name for name in names if not _is_forced_member(name)]
            if not eligible:
                raise ValueError(
                    f"Vladoon download {url} carries no non-forced subtitle member"
                )
            member = None
            if wanted is not None:
                for name in eligible:
                    # Only the member's own basename names its episode: a
                    # pack directory like ``S01E01-E07`` is a range marker
                    # for the whole archive, not the member's episode. The
                    # host reads a pinned member as-is, so the forced
                    # filtering above has to happen before any pin.
                    if _episode_tuple(_member_basename(name)) == wanted:
                        member = name
                        break
            if member is not None:
                archive["member"] = member
            else:
                # No eligible member names the episode with a searchable
                # token. Hand the archive to the host with the episode
                # number so its generic episode pick, which carries the
                # built-in matching rules, can pick looser member names.
                if wanted is not None and wanted[0] >= 0:
                    archive["season"] = wanted[0]
                if wanted is not None and wanted[1] >= 0:
                    archive["episode"] = wanted[1]
            return archive

        # A movie archive carries one member per release variant; the pick
        # is the variant whose release attributes best match the video's,
        # so the delivered member is the one the candidate's matches
        # describe. Upstream's first-subtitle rule would deliver an
        # arbitrary variant, possibly mistimed for the video's release.
        # The host reads a pinned member as-is, so forced-tagged members
        # are filtered before the ranking exactly like the episode path:
        # a forced member must not win the pick for a normal request, and
        # a forced-only archive cannot serve one.
        eligible = [name for name in names if not _is_forced_member(name)]
        if not eligible:
            raise ValueError(
                f"Vladoon download {url} carries no non-forced subtitle member"
            )
        archive["member"] = _select_movie_member(eligible, payload)
        return archive

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, max_bytes=MAX_SEARCH_BYTES):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, application/zip, */*",
                "Referer": BASE_URL + "/",
            },
        )
        # Let urllib errors surface: a network failure is not an empty
        # result and the scheduler must see the difference. The body is
        # bounded so a runaway response cannot buffer unbounded memory in
        # the worker (a download above the host's archive cap could never
        # be accepted anyway).
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"Vladoon response from {url} exceeds {max_bytes} bytes")
        return body
