"""SuperSubtitles provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "supersubtitles"
BASE_URL = "https://feliratok.eu"
HTTP_TIMEOUT_SECONDS = 15
SUPPORTED_LANGUAGES = {"hun": "hu", "eng": "en"}
ALPHA2_TO_ALPHA3 = {value: key for key, value in SUPPORTED_LANGUAGES.items()}
LANGUAGE_LABELS = {"magyar": "hun", "angol": "eng"}
SUBTITLE_EXTENSIONS = (".srt", ".sub", ".ssa", ".ass", ".vtt")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_ATTR_RE = re.compile(r"""(?P<name>[-:\w]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""", re.S)
_DOWNLOAD_LINK_RE = re.compile(r"""<a\b(?P<attrs>[^>]*\bhref\s*=\s*(?P<quote>["'])(?P<href>[^"']*action=letolt[^"']*)(?P=quote)[^>]*)>""", re.I | re.S)
_IMDB_RE = re.compile(r"(?:imdb\.com/title/|imdb_adatlap[^>]+value=[\"'])(?P<id>tt\d+)", re.I)
_INT_RE = re.compile(r"\d+")
_LOCAL_TITLE_RE = re.compile(r"""<div\b[^>]*class\s*=\s*["']magyar["'][^>]*>(?P<body>.*?)</div>""", re.I | re.S)
_ORIGINAL_TITLE_RE = re.compile(r"""<div\b[^>]*class\s*=\s*["']eredeti["'][^>]*>(?P<body>.*?)</div>""", re.I | re.S)
_SMALL_RE = re.compile(r"<small\b[^>]*>(?P<body>.*?)</small>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_TD_WITH_ID_TEMPLATE = r"""<td\b[^>]*onclick\s*=\s*["']adatlapnyitas\(['"]a_{id}['"]\)["'][^>]*>(?P<body>.*?)</td>"""
_TITLE_YEAR_RELEASE_RE = re.compile(r"^(?P<title>.*?)\s*\((?P<year>(?:19|20)\d{2})\)\s*(?:\((?P<releases>.*)\))?\s*$", re.S)
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_SEASON_EPISODE_RE = re.compile(r"\bs(?P<season>\d{1,2})e(?P<episode>\d{1,3})\b", re.I)


def build_queries(video):
    video = video or {}
    if video.get("kind") == "movie":
        return _unique_texts([video.get("title"), *list(video.get("alternative_titles") or [])])
    if video.get("kind") == "episode":
        return _unique_texts([video.get("series"), *list(video.get("alternative_series") or [])])
    return []


def parse_movie_rows(body):
    text = _decode_html(body)
    rows = []
    seen = set()
    for link_match in _DOWNLOAD_LINK_RE.finditer(text):
        href = html.unescape(link_match.group("href").strip())
        subtitle_id = _query_param(href, "felirat")
        if not subtitle_id or subtitle_id in seen:
            continue
        window = _row_window(text, link_match.start(), link_match.end())
        language = _language_from_label(_first_match_text(_SMALL_RE, window))
        original = _strip_tags(_first_group(_ORIGINAL_TITLE_RE, window))
        title, year, releases = _parse_title_year_releases(original)
        if not subtitle_id or not language or not title:
            continue
        local_title = _clean_local_title(_strip_tags(_first_group(_LOCAL_TITLE_RE, window)))
        td_texts = _row_td_texts(window, subtitle_id)
        uploader = td_texts[2] if len(td_texts) >= 3 else ""
        forced = _is_forced_text(" ".join([local_title, original, href, _query_param(href, "fnev")]))
        seen.add(subtitle_id)
        rows.append(
            {
                "subtitle_id": subtitle_id,
                "language": language,
                "title": title,
                "local_title": local_title,
                "year": year,
                "releases": releases,
                "uploader": uploader,
                "forced": forced,
                "filename": _query_param(href, "fnev"),
                "release_info": _release_info_from_parts(title, year, releases),
                "page_url": _detail_url(subtitle_id),
                "download_url": _absolute_url(href),
            }
        )
    return rows


def parse_episode_rows(body, video=None):
    data = _parse_json(body)
    if isinstance(data, dict):
        entries = list(data.values())
    elif isinstance(data, list):
        entries = data
    else:
        entries = []
    grouped = {}
    order = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        subtitle_id = str(entry.get("felirat") or "").strip()
        language = _language_from_label(entry.get("language"))
        if not subtitle_id or not language:
            continue
        title, release = _parse_episode_name(entry.get("nev") or "")
        if not title:
            title = (video or {}).get("series") or ""
        if subtitle_id not in grouped:
            order.append(subtitle_id)
            grouped[subtitle_id] = {
                "subtitle_id": subtitle_id,
                "language": language,
                "title": title,
                "season": _safe_int(entry.get("evad")),
                "episode": _safe_int(entry.get("ep")),
                "is_pack": str(entry.get("evadpakk") or "0") not in {"", "0"},
                "releases": [],
                "uploader": str(entry.get("feltolto") or "").strip(),
                "filename": str(entry.get("fnev") or "").strip(),
                "page_url": _detail_url(subtitle_id),
                "download_url": _episode_download_url(entry),
            }
        if release and release not in grouped[subtitle_id]["releases"]:
            grouped[subtitle_id]["releases"].append(release)
        if title and not grouped[subtitle_id].get("title"):
            grouped[subtitle_id]["title"] = title
    rows = []
    for subtitle_id in order:
        row = grouped[subtitle_id]
        if (video or {}).get("season") is not None:
            row["season"] = _safe_int(video.get("season")) if row["is_pack"] else row["season"]
        if (video or {}).get("episode") is not None:
            row["episode"] = _safe_int(video.get("episode")) if row["is_pack"] else row["episode"]
        row["release_info"] = _release_info_from_parts(
            row.get("title"),
            None,
            row.get("releases") or [_filename_without_extension(row.get("filename"))],
        )
        rows.append(row)
    return rows


def parse_autoname_results(body):
    data = _parse_json(body)
    rows = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        series_id = str(entry.get("ID") or entry.get("id") or "").strip()
        if not name or not series_id:
            continue
        title, year, _releases = _parse_title_year_releases(name)
        rows.append({"id": series_id, "title": title or name, "year": year, "name": name})
    return rows


def select_series_id(matches, series, year=None):
    wanted = _normalize(series)
    wanted_year = _safe_int(year)
    for match in matches or []:
        if _normalize(match.get("title")) != wanted:
            continue
        if wanted_year is not None and match.get("year") != wanted_year:
            continue
        return match.get("id")
    if wanted_year is None:
        for match in matches or []:
            if _normalize(match.get("title")) == wanted:
                return match.get("id")
    return None


def _series_id_for_query(fetch, query, video):
    autoname_url = _autoname_url(query)
    return select_series_id(parse_autoname_results(fetch(autoname_url)), query, (video or {}).get("year"))


def parse_detail_imdb_id(body):
    text = _decode_html(body)
    match = _IMDB_RE.search(text or "")
    return match.group("id").lower() if match else ""


def derive_matches(video, row):
    video = video or {}
    row = row or {}
    if video.get("kind") == "movie":
        return _movie_matches(video, row)
    if video.get("kind") == "episode":
        return _episode_matches(video, row)
    return []


class SuperSubtitlesProvider:
    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        headers["Referer"] = referer or f"{BASE_URL}/"
        request = urllib.request.Request(_request_url(url), headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def search(self, video, languages, config):
        kind = (video or {}).get("kind")
        variants = _requested_variants(languages)
        if not variants:
            return []
        if kind == "movie":
            return self._search_movie(video, variants, config)
        if kind == "episode":
            return self._search_episode(video, variants, config)
        return []

    def _search_movie(self, video, variants, config):
        results = []
        seen = set()
        requested = {(item["alpha3"], item["forced"]) for item in variants}
        for query in build_queries(video):
            _sleep(config)
            search_url = _movie_search_url(query)
            for row in parse_movie_rows(self._http_get(search_url)):
                if (row["language"], row["forced"]) not in requested:
                    continue
                if not _movie_row_matches(video, row):
                    continue
                _sleep(config)
                row = dict(row)
                row["imdb_id"] = parse_detail_imdb_id(self._http_get(row["page_url"], referer=search_url))
                matches = derive_matches(video, row)
                if _clean_imdb(video.get("imdb_id")) and row.get("imdb_id") and "imdb_id" not in matches:
                    continue
                key = (row["subtitle_id"], row["language"], row["forced"])
                if key in seen:
                    continue
                seen.add(key)
                language = _language_variant(row["language"], forced=row["forced"])
                results.append(_result(video, row, language, matches))
            if results:
                break
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _search_episode(self, video, variants, config):
        requested = {item["alpha3"] for item in variants if not item.get("forced")}
        if not requested:
            return []
        series_id = None
        for query in build_queries(video):
            _sleep(config)
            series_id = _series_id_for_query(self._http_get, query, video)
            if series_id:
                break
        if not series_id:
            return []
        _sleep(config)
        episode_url = _episode_search_url(series_id, video.get("season"), video.get("episode"))
        rows = parse_episode_rows(self._http_get(episode_url), video)
        if not rows:
            _sleep(config)
            episode_url = _episode_search_url(series_id, video.get("season"), None)
            rows = parse_episode_rows(self._http_get(episode_url), video)
        results = []
        seen = set()
        for row in _matching_episode_rows(rows, requested, video):
            item = _episode_result_from_row(self._http_get, row, video, episode_url, seen, config)
            if item is not None:
                results.append(item)
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        url = payload.get("url")
        if not url:
            raise ValueError("supersubtitles download requires url")
        body = self._http_get(url, timeout=30, referer=payload.get("page_url") or BASE_URL)
        return extract_download(body, payload)


def extract_download(body, payload=None):
    payload = dict(payload or {})
    filename = payload.get("filename") or ""
    # Reject broken responses up front: the download endpoint can answer with an empty
    # stream or an HTML/error page that would otherwise look like a successful download.
    if not body or not body.strip():
        raise ValueError("supersubtitles empty download")
    if _is_html_body(body):
        raise ValueError("supersubtitles returned an HTML/error page")
    if _is_archive_body(body):
        # Host-side extraction (Provider Hub v1.1+): hand the raw archive bytes back to the
        # host. A feliratok.eu season pack zip can hold one subtitle per episode (and per
        # release group); the host's episode-only pick cannot tell several release groups
        # for the same episode apart, so when we can list a zip we pin the member matching
        # the season+episode and the release fields the result was scored on. Otherwise
        # (rar, single member, or no clear winner) let the host pick the member by episode.
        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        member = _select_zip_member(body, payload)
        if member is not None:
            archive["member"] = member
        else:
            archive["episode"] = _safe_int(payload.get("episode"))
        return archive
    # Direct, non-archive subtitle body.
    subtitle_format = _subtitle_extension(filename) or ("srt" if _looks_like_subtitle(body) else "")
    if not subtitle_format:
        raise ValueError("supersubtitles download did not return a supported subtitle file")
    return _content_payload(body, subtitle_format)


def _is_archive_body(body):
    return _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _select_zip_member(body, payload):
    # Pin the zip member matching the requested season+episode and the scored release
    # group / resolution / source. Listing only, no extraction or decoding: the host reads
    # the named member and runs chardet. Returns None for rar (not stdlib-listable), a
    # single member (nothing to disambiguate), or when no field breaks the tie, so the
    # caller falls back to host-side episode selection.
    payload = payload or {}
    if _is_rar_archive(body) or not zipfile.is_zipfile(io.BytesIO(body or b"")):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and _subtitle_extension(name)
            and not name.rsplit("/", 1)[-1].startswith(".")
        ]
    if len(members) < 2:
        return None  # a lone member: the host's episode pick already lands here
    # Narrow to the requested episode first. The host can already do this, but a pack with
    # several release groups per episode leaves it guessing among the matches.
    season = _safe_int(payload.get("season"))
    episode = _safe_int(payload.get("episode"))
    pool = members
    if season is not None and episode is not None:
        episode_pool = [name for name in members if _member_has_episode(name, season, episode)]
        if not episode_pool and not any(_member_has_season_episode_token(name) for name in members):
            # No SxxExx/NxNN token anywhere: SuperSubtitles packs commonly name members with a
            # bare episode token (e.g. "Show.E05.720p-CAKES.srt"). Since no member carries a
            # season+episode token, a bare eNN match is unambiguous (single-season pack) and
            # lets the release tie-breaker run instead of deferring to a blind host pick.
            episode_pool = [name for name in members if _member_has_bare_episode(name, episode)]
        if not episode_pool:
            # Episode requested but absent from every member: pinning a member from another
            # episode would hard-fail the host download, so defer to host episode selection.
            return None
        pool = episode_pool
    if len(pool) < 2:
        return None  # a single episode match: host episode selection already lands here
    # Break the tie with the same fields the result was scored on, pulled from the release
    # info / filename the search built. Pin only a unique winner.
    release_text = " ".join([_coerce_text(payload.get("release_info")), _coerce_text(payload.get("filename"))])
    forced = bool(payload.get("forced"))
    best, best_score, tied = None, 0, False
    for name in pool:
        score = _member_release_score(name, release_text, forced)
        if score > best_score:
            best, best_score, tied = name, score, False
        elif score == best_score and best is not None:
            tied = True
    if best is None or best_score == 0 or tied:
        return None  # cannot confidently disambiguate; let the host pick by episode
    return best


def _member_has_episode(name, season, episode):
    # Match SxxExx as a delimited token, tolerating a separator between the season and
    # episode parts (S01E02, S01.E02, S01 E02, S01-E02), plus the NxNN form (1x02). The
    # (?!\d) guard stops a code from matching a longer number ("e2" not matching "e20").
    # We deliberately do NOT match a bare "{season}{episode:02d}" form (e.g. "213"): it
    # collides with release tokens like "720p" (S07E20 vs 720p) since the digit-only
    # lookahead still passes on a trailing letter, which is the exact regression we guard.
    text = _normalize(os.path.basename(name))
    return bool(
        re.search(rf"\bs0*{season}[\s._-]*e0*{episode}(?!\d)", text)
        or re.search(rf"(?<!\d){season}x0*{episode}(?!\d)", text)
    )


def _member_has_bare_episode(name, episode):
    # Bare episode token (E05), used by packs that omit the season, e.g.
    # "Show.E05.720p-CAKES.srt". Only consulted (see _select_zip_member) when no member
    # carries a season+episode token, so it cannot cross seasons. The (?!\d) guard keeps
    # E5 from matching E50, and the \b anchor keeps it from matching the "e" inside SxxEyy.
    text = _normalize(os.path.basename(name))
    return bool(re.search(rf"\be0*{episode}(?!\d)", text))


def _member_has_season_episode_token(name):
    # True when a member carries an explicit season+episode token (SxxEyy / NxNN): the pack
    # names episodes with their season, so a season-blind bare-eNN match would be unsafe.
    text = _normalize(os.path.basename(name))
    return bool(
        re.search(r"\bs0*\d+[\s._-]*e0*\d+(?!\d)", text)
        or re.search(r"(?<!\d)\d+x0*\d+(?!\d)", text)
    )


def _member_release_score(name, release_text, forced=False):
    # Mirror the pre-migration _subtitle_file_score weights: release group dominates,
    # then resolution, then source. Match delimited tokens, case-insensitively.
    normalized_name = _normalize(os.path.basename(name))
    # A non-forced request must never pin a member whose basename carries a delimited
    # "forced" token: the host's exact "member in namelist" check would then silently
    # deliver a forced subtitle. Drop it below the score floor so it is never chosen
    # (the caller still defers when nothing else wins). Forced requests keep resolving
    # their forced member normally.
    if not forced and re.search(r"\bforced\b", normalized_name):
        return -1
    score = 0
    release_group = _release_group_from_text(release_text)
    if release_group and re.search(rf"\b{re.escape(_normalize(release_group))}\b", normalized_name):
        score += 50
    resolution = _resolution_from_text(release_text)
    if resolution and re.search(rf"\b{re.escape(resolution)}\b", normalized_name):
        score += 15
    source = _source_token(release_text)
    if source and re.search(rf"\b{re.escape(source)}\b", normalized_name):
        score += 5
    return score


def _release_group_from_text(value):
    text = _coerce_text(value).strip()
    # Drop a trailing file extension so the group is not parsed as e.g. "SPARKS.mkv".
    text = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", text)
    # The release group is the LAST hyphen-delimited token. Anchoring to the first match
    # mis-parses titled releases: "Spider-Man.2002.720p.WEB-SPARKS" must yield "SPARKS",
    # not "Man.2002.720p.WEB" (the title hyphen).
    matches = re.findall(r"-([A-Za-z0-9][A-Za-z0-9._]+)\b", text)
    return matches[-1] if matches else ""


def _resolution_from_text(value):
    match = re.search(r"\b(?:480p|576p|720p|1080p|2160p|4k)\b", _coerce_text(value), re.I)
    return match.group(0).lower() if match else ""


def _movie_matches(video, row):
    matches = []
    if any(_title_matches(wanted, candidate) for wanted in [video.get("title"), *list(video.get("alternative_titles") or [])] for candidate in [row.get("title"), row.get("local_title")]):
        matches.append("title")
    wanted_year = _safe_int(video.get("year"))
    if wanted_year is not None and wanted_year == _safe_int(row.get("year")):
        matches.append("year")
    if _clean_imdb(video.get("imdb_id")) and _clean_imdb(video.get("imdb_id")) == _clean_imdb(row.get("imdb_id")):
        matches.append("imdb_id")
    matches.extend(_release_matches(video, _row_release_text(row)))
    return matches


def _episode_matches(video, row):
    matches = []
    if _title_matches(video.get("series"), row.get("title")):
        matches.append("series")
    if _safe_int(video.get("season")) is not None and _safe_int(video.get("season")) == _safe_int(row.get("season")):
        matches.append("season")
    if _safe_int(video.get("episode")) is not None and _safe_int(video.get("episode")) == _safe_int(row.get("episode")):
        matches.append("episode")
    if _clean_imdb(video.get("series_imdb_id")) and _clean_imdb(video.get("series_imdb_id")) == _clean_imdb(row.get("imdb_id")):
        matches.append("series_imdb_id")
    matches.extend(_release_matches(video, _row_release_text(row)))
    return matches


def _episode_row_matches_requested(video, row):
    wanted_season = _safe_int((video or {}).get("season"))
    wanted_episode = _safe_int((video or {}).get("episode"))
    if wanted_season is not None and _safe_int((row or {}).get("season")) != wanted_season:
        return False
    if wanted_episode is not None and _safe_int((row or {}).get("episode")) != wanted_episode:
        return False
    return True


def _matching_episode_rows(rows, requested, video):
    for row in rows:
        if row["language"] not in requested:
            continue
        if not _episode_row_matches_requested(video, row):
            continue
        yield row


def _episode_result_from_row(fetch, row, video, episode_url, seen, config):
    _sleep(config)
    row = dict(row)
    _apply_matched_release(video, row)
    row["imdb_id"] = parse_detail_imdb_id(fetch(row["page_url"], referer=episode_url))
    matches = derive_matches(video, row)
    if _clean_imdb(video.get("series_imdb_id")) and row.get("imdb_id") and "series_imdb_id" not in matches:
        return None
    key = (row["subtitle_id"], row["language"])
    if key in seen:
        return None
    seen.add(key)
    return _result(video, row, _language_variant(row["language"]), matches)


def _apply_matched_release(video, row):
    matched_release = _best_release_for_video(video, (row or {}).get("releases") or [])
    if not matched_release:
        return
    row["matched_release"] = matched_release
    row["release_info"] = _release_info_from_parts(row.get("title"), None, [matched_release])


def _best_release_for_video(video, releases):
    releases = _unique_texts(releases)
    if not releases:
        return ""
    return max(releases, key=lambda release: _release_score(video, release))


def _release_score(video, release):
    matches = set(_release_matches(video or {}, release))
    score = 0
    if "release_group" in matches:
        score += 50
    if "resolution" in matches:
        score += 15
    if "source" in matches:
        score += 5
    return score


def _release_matches(video, release_text):
    matches = []
    normalized = _normalize(release_text)
    if _release_group_matches_release(video, normalized):
        matches.append("release_group")
    if _release_resolution_matches(video, normalized):
        matches.append("resolution")
    if _release_source_matches(video, normalized):
        matches.append("source")
    return matches


def _release_group_matches_release(video, normalized_release):
    release_group = _normalize((video or {}).get("release_group"))
    return bool(release_group and re.search(rf"\b{re.escape(release_group)}\b", normalized_release))


def _release_resolution_matches(video, normalized_release):
    resolution = _normalize((video or {}).get("resolution"))
    return bool(resolution and re.search(rf"\b{re.escape(resolution)}\b", normalized_release))


def _release_source_matches(video, normalized_release):
    source = _source_token((video or {}).get("source"))
    return bool(source and source in normalized_release)


def _result(video, row, language, matches):
    score = 45
    score += 15 if "title" in matches or "series" in matches else 0
    score += 10 if "year" in matches else 0
    score += 15 if "imdb_id" in matches or "series_imdb_id" in matches else 0
    score += 10 if "episode" in matches else 0
    score += 5 if "release_group" in matches else 0
    score = min(score, 100)
    filename = row.get("filename") or _generated_filename(row, language)
    release_info = _result_release_info(row)
    return {
        "provider": PROVIDER_ID,
        "id": f"{PROVIDER_ID}-{row['subtitle_id']}-{language['alpha3']}{'-forced' if language.get('forced') else ''}",
        "language": dict(language),
        "release_info": release_info,
        "filename": filename,
        "matches": matches,
        "score": score,
        "score_without_hash": score,
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "page_link": row.get("page_url"),
        "display": _result_display(row, release_info),
        "provider_payload": _provider_payload(row, language, filename, release_info),
    }


def _result_release_info(row):
    return row.get("release_info") or _row_release_text(row)


def _result_display(row, release_info):
    return {
        "source": "feliratok.eu",
        "title": row.get("title"),
        "release": release_info,
        "uploader": row.get("uploader"),
    }


def _provider_payload(row, language, filename, release_info):
    return {
        "provider": PROVIDER_ID,
        "schema": 1,
        "subtitle_id": row["subtitle_id"],
        "url": row.get("download_url"),
        "page_url": row.get("page_url"),
        "filename": filename,
        "release_info": release_info,
        "language": language["alpha3"],
        "forced": bool(language.get("forced")),
        "season": row.get("season"),
        "episode": row.get("episode"),
        "is_pack": bool(row.get("is_pack")),
    }


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially a legacy codepage that never fails to decode) only reintroduces
    # mojibake. Leave encoding unset and let the host normalize.
    content = content or b""
    return {
        "content_b64": base64.b64encode(content).decode("ascii"),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_type": "text/plain",
        "format": subtitle_format or "srt",
        "empty": False,
    }


def _requested_variants(languages):
    variants = []
    seen = set()
    for language in languages or []:
        if (language or {}).get("hi"):
            continue
        alpha3 = _alpha3_for_language(language)
        if alpha3 not in SUPPORTED_LANGUAGES:
            continue
        variant = _language_variant(alpha3, bool((language or {}).get("forced")))
        key = (variant["alpha3"], variant["forced"])
        if key not in seen:
            seen.add(key)
            variants.append(variant)
    return variants


def _language_variant(alpha3, forced=False):
    return {
        "alpha3": alpha3,
        "alpha2": SUPPORTED_LANGUAGES[alpha3],
        "hi": False,
        "forced": bool(forced),
    }


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3 = str(language.get("alpha3") or "").lower()
    alpha2 = str(language.get("alpha2") or "").lower()
    return alpha3 if alpha3 in SUPPORTED_LANGUAGES else ALPHA2_TO_ALPHA3.get(alpha2)


def _language_from_label(label):
    return LANGUAGE_LABELS.get(_normalize(label))


def _parse_title_year_releases(value):
    value = _coerce_text(value).strip()
    match = _TITLE_YEAR_RELEASE_RE.match(value)
    if not match:
        return value, None, []
    title = _WS_RE.sub(" ", match.group("title")).strip()
    releases = _split_releases(match.group("releases") or "")
    return title, int(match.group("year")), releases


def _parse_episode_name(value):
    text = _coerce_text(value).strip()
    if not text:
        return "", ""
    match = re.match(r"^(.*?)\s(?:-\s\d+x\d+|\(Season\s+\d+\))?\s\((.*)\)$", text, re.I)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    title = text.split(" (Season", 1)[0].strip()
    release_matches = re.findall(r"\(([^()]*)\)", text)
    release = release_matches[-1].strip() if release_matches else ""
    return title, release


def _split_releases(value):
    return [part.strip() for part in _coerce_text(value).split(",") if part.strip()]


def _row_window(text, start, end):
    row_start = text.rfind("<tr", 0, start)
    if row_start < 0:
        row_start = max(0, start - 2000)
    row_end = text.find("</tr>", end)
    if row_end < 0:
        row_end = min(len(text), end + 2000)
    else:
        row_end += len("</tr>")
    return text[row_start:row_end]


def _row_td_texts(window, subtitle_id):
    pattern = re.compile(_TD_WITH_ID_TEMPLATE.format(id=re.escape(subtitle_id)), re.I | re.S)
    return [_strip_tags(match.group("body")) for match in pattern.finditer(window)]


def _movie_row_matches(video, row):
    wanted_year = _safe_int((video or {}).get("year"))
    if wanted_year is not None and row.get("year") is not None and wanted_year != row.get("year"):
        return False
    wanted_titles = [video.get("title"), *list(video.get("alternative_titles") or [])]
    return any(_title_matches(wanted, candidate) for wanted in wanted_titles for candidate in [row.get("title"), row.get("local_title")])


def _row_release_text(row):
    releases = [row.get("matched_release")] if row.get("matched_release") else row.get("releases") or []
    return " ".join([row.get("release_info") or "", row.get("filename") or "", " ".join(releases)]).strip()


def _release_info_from_parts(title, year, releases):
    base = title or ""
    if year:
        base = f"{base} ({year})"
    release_part = ", ".join(releases or [])
    return f"{base} ({release_part})" if release_part else base


def _movie_search_url(query):
    return f"{BASE_URL}/index.php?search={urllib.parse.quote_plus(_coerce_text(query).strip())}&soriSorszam=&nyelv=&tab=film"


def _autoname_url(query):
    params = urllib.parse.urlencode({"term": _coerce_text(query).strip(), "nyelv": "0", "action": "autoname"})
    return f"{BASE_URL}/index.php?{params}"


def _episode_search_url(series_id, season, episode=None):
    params = {"action": "xbmc", "sid": str(series_id), "ev": str(_safe_int(season) or season or "")}
    if episode is not None:
        params["rtol"] = str(_safe_int(episode) or episode)
    return f"{BASE_URL}/index.php?{urllib.parse.urlencode(params)}"


def _detail_url(subtitle_id):
    return f"{BASE_URL}/index.php?tipus=adatlap&azon=a_{subtitle_id}"


def _episode_download_url(entry):
    params = {"action": "letolt"}
    filename = str(entry.get("fnev") or "").strip()
    if filename:
        params["fnev"] = filename
    params["felirat"] = str(entry.get("felirat") or "").strip()
    return f"{BASE_URL}/index.php?{urllib.parse.urlencode(params)}"


def _absolute_url(href):
    return urllib.parse.urljoin(BASE_URL + "/", html.unescape(href or ""))


def _request_url(url):
    parsed = urllib.parse.urlsplit(html.unescape(url or ""))
    query = urllib.parse.quote(parsed.query, safe="=&%+")
    path = urllib.parse.quote(parsed.path, safe="/%")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, parsed.fragment))


def _query_param(url, name):
    parsed = urllib.parse.urlparse(html.unescape(url or ""))
    values = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return values.get(name, [""])[0]


def _parse_json(body):
    try:
        return json.loads(_decode_html(body))
    except (TypeError, json.JSONDecodeError):
        return None


def _first_group(pattern, text):
    match = pattern.search(text or "")
    return match.group("body") if match else ""


def _first_match_text(pattern, text):
    return _strip_tags(_first_group(pattern, text))


def _strip_tags(value):
    text = _TAG_RE.sub("", html.unescape(_coerce_text(value)))
    return _WS_RE.sub(" ", text).strip()


def _clean_local_title(value):
    value = _coerce_text(value).strip()
    return re.sub(r"\s*\([^)]*SubRip[^)]*\)", "", value, flags=re.I).strip()


def _is_forced_text(value):
    normalized = _normalize(value)
    return "szinkronoshoz" in normalized or "forced" in normalized


def _decode_html(body):
    if isinstance(body, str):
        return body
    body = body or b""
    for encoding in ("utf-8", "iso-8859-2", "cp1250"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _coerce_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return _decode_html(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(_coerce_text(item) for item in value if item not in (None, ""))
    return str(value)


def _title_matches(wanted, candidate):
    return bool(wanted and candidate and _normalize(wanted) == _normalize(candidate))


def _normalize(value):
    return _NON_ALNUM_RE.sub(" ", _coerce_text(value).lower()).strip()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_imdb(value):
    value = _coerce_text(value).strip().lower().rstrip("/")
    if not value:
        return ""
    match = re.search(r"(tt\d+)", value)
    return match.group(1) if match else value


def _filename_without_extension(filename):
    basename = os.path.basename(urllib.parse.urlparse(filename or "").path)
    return os.path.splitext(basename)[0]


def _generated_filename(row, language):
    title = _slug(row.get("title"))
    if row.get("season") and row.get("episode"):
        media = f"s{int(row['season']):02d}e{int(row['episode']):02d}"
    else:
        media = str(row.get("year") or "movie")
    suffix = language["alpha2"] + (".forced" if language.get("forced") else "")
    return f"{PROVIDER_ID}.{title}.{media}.{suffix}.zip"


def _slug(value):
    value = _normalize(value) or "subtitle"
    return re.sub(r"\s+", "-", value).strip("-")[:80] or "subtitle"


def _unique_texts(values):
    results = []
    for value in values:
        text = _coerce_text(value).strip()
        if text and text not in results:
            results.append(text)
    return results


def _format_from_filename(filename):
    return _subtitle_extension(filename) or "srt"


def _subtitle_extension(filename):
    extension = os.path.splitext(urllib.parse.urlparse(filename or "").path)[1].lower()
    return extension[1:] if extension in SUBTITLE_EXTENSIONS else ""


def _looks_like_subtitle(body):
    sample = (body or b"")[:4096].decode("utf-8", errors="ignore").lower()
    return "-->" in sample or "[script info]" in sample or "{\\an" in sample


def _is_rar_archive(body):
    return (body or b"").startswith(b"Rar!\x1a\x07\x00") or (body or b"").startswith(b"Rar!\x1a\x07\x01\x00")


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


def _source_token(value):
    normalized = _normalize(value)
    if "web" in normalized:
        return "web"
    if "bluray" in normalized or "blu ray" in normalized or "bdrip" in normalized or "brrip" in normalized:
        return "bluray"
    if "hdtv" in normalized:
        return "hdtv"
    return ""


def _sleep(config):
    try:
        delay_ms = int((config or {}).get("request_delay_ms") or 0)
    except (TypeError, ValueError):
        delay_ms = 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)
