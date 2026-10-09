"""iSubtitles.org provider for the Bazarr+ Provider Hub catalog."""

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

PROVIDER_ID = "isubtitles"
BASE_URL = "https://isubtitles.org"
HTTP_TIMEOUT_SECONDS = 15
MAX_TITLE_PAGES = 3
MAX_RESULTS = 25
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

LANGUAGES = {
    "aze": {"alpha2": "az", "slug": "azerbaijani", "name": "Azerbaijani"},
    "ara": {"alpha2": "ar", "slug": "arabic", "name": "Arabic"},
    "bel": {"alpha2": "be", "slug": "belarusian", "name": "Belarusian"},
    "ben": {"alpha2": "bn", "slug": "bengali", "name": "Bengali"},
    "bos": {"alpha2": "bs", "slug": "bosnian", "name": "Bosnian"},
    "bul": {"alpha2": "bg", "slug": "bulgarian", "name": "Bulgarian"},
    "cat": {"alpha2": "ca", "slug": "catalan", "name": "Catalan"},
    "ces": {"alpha2": "cs", "slug": "czech", "name": "Czech"},
    "dan": {"alpha2": "da", "slug": "danish", "name": "Danish"},
    "deu": {"alpha2": "de", "slug": "german", "name": "German"},
    "ell": {"alpha2": "el", "slug": "greek", "name": "Greek"},
    "eng": {"alpha2": "en", "slug": "english", "name": "English"},
    "epo": {"alpha2": "eo", "slug": "esperanto", "name": "Esperanto"},
    "est": {"alpha2": "et", "slug": "estonian", "name": "Estonian"},
    "eus": {"alpha2": "eu", "slug": "basque", "name": "Basque"},
    "fas": {"alpha2": "fa", "slug": "farsi-persian", "name": "Farsi/Persian"},
    "fil": {"alpha2": "tl", "slug": "tagalog", "name": "Tagalog"},
    "fin": {"alpha2": "fi", "slug": "finnish", "name": "Finnish"},
    "fra": {"alpha2": "fr", "slug": "french", "name": "French"},
    "heb": {"alpha2": "he", "slug": "hebrew", "name": "Hebrew"},
    "hin": {"alpha2": "hi", "slug": "hindi", "name": "Hindi"},
    "hrv": {"alpha2": "hr", "slug": "croatian", "name": "Croatian"},
    "hun": {"alpha2": "hu", "slug": "hungarian", "name": "Hungarian"},
    "hye": {"alpha2": "hy", "slug": "armenian", "name": "Armenian"},
    "ind": {"alpha2": "id", "slug": "indonesian", "name": "Indonesian"},
    "isl": {"alpha2": "is", "slug": "icelandic", "name": "Icelandic"},
    "ita": {"alpha2": "it", "slug": "italian", "name": "Italian"},
    "jpn": {"alpha2": "ja", "slug": "japanese", "name": "Japanese"},
    "kal": {"alpha2": "kl", "slug": "greenlandic", "name": "Greenlandic"},
    "kan": {"alpha2": "kn", "slug": "kannada", "name": "Kannada"},
    "kat": {"alpha2": "ka", "slug": "georgian", "name": "Georgian"},
    "khm": {"alpha2": "km", "slug": "cambodian-khmer", "name": "Cambodian/Khmer"},
    "kor": {"alpha2": "ko", "slug": "korean", "name": "Korean"},
    "kur": {"alpha2": "ku", "slug": "kurdish", "name": "Kurdish"},
    "lav": {"alpha2": "lv", "slug": "latvian", "name": "Latvian"},
    "lit": {"alpha2": "lt", "slug": "lithuanian", "name": "Lithuanian"},
    "mal": {"alpha2": "ml", "slug": "malayalam", "name": "Malayalam"},
    "mkd": {"alpha2": "mk", "slug": "macedonian", "name": "Macedonian"},
    "mni": {"alpha2": "mni", "slug": "manipuri", "name": "Manipuri"},
    "mon": {"alpha2": "mn", "slug": "mongolian", "name": "Mongolian"},
    "msa": {"alpha2": "ms", "slug": "malay", "name": "Malay"},
    "mya": {"alpha2": "my", "slug": "burmese", "name": "Burmese"},
    "nep": {"alpha2": "ne", "slug": "nepali", "name": "Nepali"},
    "nld": {"alpha2": "nl", "slug": "dutch", "name": "Dutch"},
    "nor": {"alpha2": "no", "slug": "norwegian", "name": "Norwegian"},
    "pan": {"alpha2": "pa", "slug": "punjabi", "name": "Punjabi"},
    "pol": {"alpha2": "pl", "slug": "polish", "name": "Polish"},
    "por": {"alpha2": "pt", "slug": "portuguese", "name": "Portuguese"},
    "pus": {"alpha2": "ps", "slug": "pashto", "name": "Pashto"},
    "rhg": {"alpha2": "rhg", "slug": "rohingya", "name": "Rohingya"},
    "ron": {"alpha2": "ro", "slug": "romanian", "name": "Romanian"},
    "rus": {"alpha2": "ru", "slug": "russian", "name": "Russian"},
    "sin": {"alpha2": "si", "slug": "sinhala", "name": "Sinhala"},
    "slk": {"alpha2": "sk", "slug": "slovak", "name": "Slovak"},
    "slv": {"alpha2": "sl", "slug": "slovenian", "name": "Slovenian"},
    "som": {"alpha2": "so", "slug": "somali", "name": "Somali"},
    "spa": {"alpha2": "es", "slug": "spanish", "name": "Spanish"},
    "sqi": {"alpha2": "sq", "slug": "albanian", "name": "Albanian"},
    "srp": {"alpha2": "sr", "slug": "serbian", "name": "Serbian"},
    "sun": {"alpha2": "su", "slug": "sundanese", "name": "Sundanese"},
    "swa": {"alpha2": "sw", "slug": "swahili", "name": "Swahili"},
    "swe": {"alpha2": "sv", "slug": "swedish", "name": "Swedish"},
    "tam": {"alpha2": "ta", "slug": "tamil", "name": "Tamil"},
    "tel": {"alpha2": "te", "slug": "telugu", "name": "Telugu"},
    "tha": {"alpha2": "th", "slug": "thai", "name": "Thai"},
    "tur": {"alpha2": "tr", "slug": "turkish", "name": "Turkish"},
    "ukr": {"alpha2": "uk", "slug": "ukrainian", "name": "Ukrainian"},
    "urd": {"alpha2": "ur", "slug": "urdu", "name": "Urdu"},
    "vie": {"alpha2": "vi", "slug": "vietnamese", "name": "Vietnamese"},
    "yor": {"alpha2": "yo", "slug": "yoruba", "name": "Yoruba"},
    "zho": {"alpha2": "zh", "slug": "chinese-bg-code", "name": "Chinese"},
}
_SLUG_TO_ALPHA3 = {value["slug"]: key for key, value in LANGUAGES.items()}
_SLUG_TO_ALPHA3.update(
    {
        "big-5-code": "zho",
        "brazillian-portuguese": "por",
        "ukranian": "ukr",
    }
)
_ALPHA2_TO_ALPHA3 = {value["alpha2"]: key for key, value in LANGUAGES.items()}

# isubtitles.org lists Brazilian Portuguese on a separate slug from the generic
# Portuguese page. Bazarr+ requests carry country_alpha2 "BR" (alpha3 "por") for it.
_BRAZIL_SLUG = "brazillian-portuguese"
_BRAZIL_COUNTRY = "BR"

_MOVIE_LINK_RE = re.compile(
    rb"<h3>\s*<a\b[^>]*href=['\"](?P<href>/[^'\"]+-subtitles)['\"][^>]*>(?P<title>.*?)</a>\s*</h3>",
    re.I | re.S,
)
_DOWNLOAD_ROW_RE = re.compile(
    rb"<tr\b[^>]*>(?P<body>(?:(?!</tr>).)*?/download/(?:(?!</tr>).)*)</tr>",
    re.I | re.S,
)
_DOWNLOAD_RE = re.compile(
    rb"href=['\"](?P<href>/download/(?P<slug>[^/]+)/(?P<language>[^/]+)/(?P<id>\d+))['\"]",
    re.I,
)
_LINK_TEXT_RE = re.compile(rb"<a\b[^>]*>(?P<text>.*?)</a>", re.I | re.S)
_TAG_RE = re.compile(rb"<[^>]+>")
_WS_BYTES_RE = re.compile(rb"\s+")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_YEAR_RE = re.compile(r"\((\d{4})\)")


def build_queries(video):
    video = video or {}
    if video.get("kind") == "movie":
        title = _coerce_text(video.get("title"))
        if not title:
            return []
        year = video.get("year")
        return [f"{title} {year}", title] if year else [title]
    if video.get("kind") == "episode":
        series = _coerce_text(video.get("series"))
        if not series:
            return []
        try:
            tag = f"S{int(video.get('season')):02d}E{int(video.get('episode')):02d}"
        except (TypeError, ValueError):
            return []
        return [f"{series} {tag}", series]
    return []


def parse_search_results(body):
    results = []
    seen = set()
    for match in _MOVIE_LINK_RE.finditer(body or b""):
        href = _decode(match.group("href"))
        slug = href.rsplit("/", 1)[-1].removesuffix("-subtitles")
        if slug in seen:
            continue
        title = _strip_tags(match.group("title"))
        seen.add(slug)
        results.append(
            {
                "slug": slug,
                "title": title,
                "year": _year_from_title(title),
                "url": _absolute_url(href),
            }
        )
    return results


def parse_subtitle_rows(body):
    rows = []
    for row_match in _DOWNLOAD_ROW_RE.finditer(body or b""):
        row = row_match.group("body")
        download_match = _DOWNLOAD_RE.search(row)
        if not download_match:
            continue
        language_slug = _decode(download_match.group("language")).lower()
        alpha3 = _SLUG_TO_ALPHA3.get(language_slug)
        if not alpha3:
            continue
        release_cell = _cell_by_title(row, "Release / Movie")
        release_names = [_strip_tags(match.group("text")) for match in _LINK_TEXT_RE.finditer(release_cell)]
        release_names = [name for name in release_names if name]
        if not release_names:
            continue
        subtitle_id = _decode(download_match.group("id"))
        slug = _decode(download_match.group("slug"))
        rows.append(
            {
                "subtitle_id": subtitle_id,
                "slug": slug,
                "language": alpha3,
                "language_slug": language_slug,
                "release_info": "\n".join(release_names),
                "download_url": _absolute_url(_decode(download_match.group("href"))),
                "page_url": _absolute_url(f"/{slug}/{language_slug}/{subtitle_id}"),
                "file_count": _int_from_text(_strip_tags(_cell_by_title(row, "File"))),
                "size": _strip_tags(_cell_by_title(row, "Size")),
                "updated": _strip_tags(_cell_by_title(row, "Created")),
                "comment": _strip_tags(_cell_by_title(row, "Comment")),
            }
        )
    return rows


def derive_matches(video, candidate_title):
    if not video:
        return []
    candidate_norm = _normalize(candidate_title)
    candidate_tokens = set(_tokens(candidate_title))
    matches = []
    if video.get("kind") == "movie":
        title_tokens = _tokens(video.get("title"))
        if title_tokens and all(token in candidate_tokens for token in title_tokens):
            matches.append("title")
        if video.get("year") and str(video.get("year")) in candidate_tokens:
            matches.append("year")
        return matches

    if video.get("kind") == "episode":
        series_tokens = _tokens(video.get("series"))
        if series_tokens and all(token in candidate_tokens for token in series_tokens):
            matches.append("series")
        try:
            season = int(video.get("season"))
            episode = int(video.get("episode"))
        except (TypeError, ValueError):
            season = episode = None
        if season is not None and _season_tag_in(candidate_norm, season):
            matches.append("season")
        if season is not None and episode is not None and _episode_tag_in(candidate_norm, season, episode):
            matches.append("episode")
        title_tokens = _tokens(video.get("title"))
        if title_tokens and len(title_tokens) > 1 and all(token in candidate_tokens for token in title_tokens):
            matches.append("title")
    return matches


class ISubtitlesProvider:
    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def search(self, video, languages, config):
        plans = _language_plans(languages)
        if not plans:
            return []
        results = []
        seen = set()
        for query in build_queries(video):
            _sleep(config)
            search_url = f"{BASE_URL}/search?{urllib.parse.urlencode({'kwd': query})}"
            title_pages = _rank_title_pages(video, parse_search_results(self._http_get(search_url)))
            for title_page in title_pages[:MAX_TITLE_PAGES]:
                for plan in plans:
                    list_url = f"{BASE_URL}/{title_page['slug']}/{plan['slug']}"
                    _sleep(config)
                    rows = parse_subtitle_rows(self._http_get(list_url, referer=search_url))
                    for row in rows:
                        if not _row_matches_plan(row, plan):
                            continue
                        if not _row_matches_video(video, row, title_page):
                            continue
                        key = (row["subtitle_id"], row["language"], plan.get("country") or "")
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(self._result(video, title_page, row, plan.get("country")))
                        if len(results) >= MAX_RESULTS:
                            return _sort_results(results)
                if results:
                    return _sort_results(results)
            if results:
                return _sort_results(results)
        return _sort_results(results)

    def _result(self, video, title_page, row, country=None):
        language = LANGUAGES[row["language"]]
        candidate_title = f"{title_page['title']} {row['release_info']} {row.get('comment', '')}"
        matches = derive_matches(video, candidate_title)
        score = _score_from_matches(video, matches, row)
        filename = f"isubtitles.{_slug(row['release_info'])}.{language['alpha2']}.zip"
        language_block = {
            "alpha3": row["language"],
            "alpha2": language["alpha2"],
            "hi": _looks_hearing_impaired(row),
            "forced": False,
        }
        result_id = f"isubtitles-{row['subtitle_id']}-{row['language']}"
        if country:
            language_block["country_alpha2"] = country
            result_id = f"{result_id}-{country}"
        return {
            "provider": PROVIDER_ID,
            "id": result_id,
            "language": language_block,
            "release_info": row["release_info"],
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": _looks_hearing_impaired(row),
            "page_link": row["page_url"],
            "display": {
                "source": "isubtitles",
                "title": title_page["title"],
                "release": row["release_info"],
                "size": row["size"],
                "updated": row["updated"],
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": row["subtitle_id"],
                "url": row["download_url"],
                "page_url": row["page_url"],
                "filename": filename,
                "season": (video or {}).get("season"),
                "episode": (video or {}).get("episode"),
                "language": row["language"],
                **({"country_alpha2": country} if country else {}),
            },
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        url = payload.get("url")
        if not url:
            raise ValueError("isubtitles download requires url")
        body = self._http_get(url, referer=payload.get("page_url"))
        return extract_download(body, payload)


def extract_download(body, payload=None):
    payload = payload or {}
    if not body:
        raise ValueError("isubtitles download returned an empty body")
    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        # Host-side extraction (Provider Hub v1.1+): list the zip cheaply with stdlib to
        # pick the requested member, then hand the raw archive bytes back to the host,
        # which extracts the member and detects the encoding via Subtitle.normalize().
        with zipfile.ZipFile(stream) as archive:
            selected = select_subtitle_file(archive.namelist(), payload)
        return _archive_payload(body, member=selected)
    if _is_rar_archive(body) or _is_7z_archive(body):
        # rar/7z cannot be listed with stdlib, so let the host pick the member by episode.
        return _archive_payload(body, episode=payload.get("episode"))
    subtitle_format = _subtitle_extension(payload.get("filename", ""))
    if not subtitle_format or _looks_like_html(body):
        raise ValueError("isubtitles download did not return a supported subtitle file")
    return _content_payload(body, subtitle_format)


def _archive_payload(body, member=None, episode=None):
    payload = {
        "archive_b64": _base64.b64encode(body).decode("ascii"),
        "archive_sha256": _hashlib.sha256(body).hexdigest(),
    }
    if member is not None:
        payload["member"] = member
    else:
        payload["episode"] = episode
    return payload


def _is_rar_archive(body):
    return bool(body) and body.startswith(b"Rar!")


def _is_7z_archive(body):
    return bool(body) and body.startswith(b"7z\xbc\xaf\x27\x1c")


def select_subtitle_file(names, payload):
    candidates = [name for name in names if _subtitle_extension(name)]
    if not candidates:
        raise ValueError("isubtitles archive contains no supported subtitle files")
    try:
        season = int((payload or {}).get("season"))
        episode = int((payload or {}).get("episode"))
    except (TypeError, ValueError):
        season = episode = None
    if season is None or episode is None:
        return candidates[0]

    def score(name):
        normalized_path = _normalize(name)
        if _episode_tag_in(normalized_path, season, episode):
            return 100
        if _season_tag_in(normalized_path, season) and _numeric_episode_filename(name, episode):
            return 90
        if _has_season_marker(normalized_path):
            return 0
        if re.search(rf"\be0*{episode}\b", normalized_path):
            return 80
        if _numeric_episode_filename(name, episode):
            return 70
        return 0

    scored = [(score(name), index, name) for index, name in enumerate(candidates)]
    best_score, _index, best_name = max(scored, key=lambda item: (item[0], -item[1]))
    has_explicit_marker = any(
        _has_season_marker(_normalize(name)) or _has_episode_marker(_normalize(name))
        for name in candidates
    )
    if best_score <= 0 and (len(candidates) > 1 or has_explicit_marker):
        raise ValueError("isubtitles archive contains no subtitle file for the requested episode")
    return best_name


def _rank_title_pages(video, pages):
    ranked = []
    wanted_tokens = _tokens((video or {}).get("series") or (video or {}).get("title"))
    wanted_norm = _normalize((video or {}).get("series") or (video or {}).get("title"))
    wanted_year = _safe_int((video or {}).get("year"))
    for index, page in enumerate(pages):
        title_without_year = _YEAR_RE.sub("", page["title"]).strip()
        page_tokens = set(_tokens(title_without_year))
        score = 0
        if wanted_tokens and all(token in page_tokens for token in wanted_tokens):
            score = 80
        if wanted_norm and _normalize(title_without_year) == wanted_norm:
            score = 110
        if wanted_year is not None and page.get("year") == wanted_year:
            score += 10
        if score:
            ranked.append((page, score, index))
    ranked.sort(key=lambda item: (-item[1], item[2]))
    return [page for page, _score, _index in ranked]


def _row_matches_video(video, row, title_page):
    video = video or {}
    candidate_title = f"{title_page['title']} {row['release_info']} {row.get('comment', '')}"
    matches = derive_matches(video, candidate_title)
    if video.get("kind") == "movie":
        wanted_year = _safe_int(video.get("year"))
        candidate_year = title_page.get("year")
        if wanted_year is not None and candidate_year is not None and candidate_year != wanted_year:
            return False
        return "title" in matches
    if video.get("kind") != "episode" or "series" not in matches:
        return False
    if "episode" in matches:
        return True
    season = _safe_int(video.get("season"))
    if season is not None and _has_episode_marker_for_season(_normalize(candidate_title), season):
        return False
    return "season" in matches and row.get("file_count", 0) > 1


def _score_from_matches(video, matches, row):
    if (video or {}).get("kind") == "movie":
        return 95 if "year" in matches else 85
    if "episode" in matches:
        return 95
    if "season" in matches and row.get("file_count", 0) > 1:
        return 85
    return 70


def _sort_results(results):
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _cell_by_title(row, title):
    pattern = re.compile(
        rb"<td\b[^>]*data-title=['\"]" + re.escape(title.encode("utf-8")) + rb"['\"][^>]*>(?P<body>.*?)</td>",
        re.I | re.S,
    )
    match = pattern.search(row or b"")
    return match.group("body") if match else b""


def _season_tag_in(candidate_norm, season):
    season = int(season)
    return (
        re.search(rf"\bs0*{season}(?=\s*e|\W|$)", candidate_norm) is not None
        or re.search(rf"\bseason\s+0*{season}\b", candidate_norm) is not None
    )


def _episode_tag_in(candidate_norm, season, episode):
    season = int(season)
    episode = int(episode)
    return episode in _episode_numbers_after_season(candidate_norm, season)


def _has_season_marker(candidate_norm):
    return (
        re.search(r"\bs0*\d+(?=\s*e|\b)", candidate_norm) is not None
        or re.search(r"\b0*\d+\s*x\s*0*\d+\b", candidate_norm) is not None
        or re.search(r"\bseason\s+0*\d+\b", candidate_norm) is not None
    )


def _has_episode_marker_for_season(candidate_norm, season):
    return bool(_episode_numbers_after_season(candidate_norm, int(season)))


def _has_episode_marker(candidate_norm):
    return (
        re.search(r"\bs0*\d+\s*e\s*0*\d{1,3}(?:(?:\s*e\s*|\s+)0*\d{1,3})*\b", candidate_norm)
        is not None
        or re.search(r"\b0*\d+\s*x\s*0*\d{1,3}(?:(?:\s*x\s*|\s+)0*\d{1,3})*\b", candidate_norm)
        is not None
        or re.search(r"\be0*\d+\b", candidate_norm) is not None
        or re.search(
            r"\bseason\s+0*\d+\s+(?:episode\s+|e\s*)0*\d{1,3}"
            r"(?:(?:\s+(?:episode\s+|e\s*)|\s+)0*\d{1,3})*\b",
            candidate_norm,
        )
        is not None
    )


def _episode_numbers_after_season(candidate_norm, season):
    numbers = set()
    patterns = (
        rf"\bs0*{season}\s*e\s*(?P<episodes>0*\d{{1,3}}(?:(?:\s*e\s*|\s+)0*\d{{1,3}})*)\b",
        rf"\b0*{season}\s*x\s*(?P<episodes>0*\d{{1,3}}(?:(?:\s*x\s*|\s+)0*\d{{1,3}})*)\b",
        rf"\bseason\s+0*{season}\s+(?:episode\s+|e\s*)"
        rf"(?P<episodes>0*\d{{1,3}}(?:(?:\s+(?:episode|e)\s+|\s+)0*\d{{1,3}})*)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, candidate_norm):
            for value in re.findall(r"\d+", match.group("episodes")):
                numbers.add(int(value))
    return numbers


def _numeric_episode_filename(name, episode):
    stem = os.path.splitext(os.path.basename(name or ""))[0]
    return _safe_int(_normalize(stem)) == int(episode)


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


def _content_type(subtitle_format):
    if subtitle_format in {"ass", "ssa"}:
        return "text/x-ssa"
    if subtitle_format == "vtt":
        return "text/vtt"
    return "application/x-subrip"


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3, _country = _alpha3_country_for_language(language)
    return alpha3


def _alpha3_country_for_language(language):
    if not isinstance(language, dict):
        return None, None
    alpha3 = (language.get("alpha3") or "").lower()
    country = (language.get("country_alpha2") or language.get("country") or "").upper()
    if "-" in alpha3 and not country:
        alpha3, suffix = alpha3.split("-", 1)
        country = suffix.upper()
    if not alpha3:
        alpha3 = _ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())
    return alpha3, (country or None)


def _language_plans(languages):
    """Map requested language payloads to listing-page fetch plans.

    Brazilian Portuguese (alpha3 "por" + country_alpha2 "BR") lives on its own
    slug, so it gets a dedicated plan that targets the brazillian-portuguese page
    and carries the BR country through to the result shape.
    """
    plans = []
    seen = set()
    for language in languages or []:
        alpha3, country = _alpha3_country_for_language(language)
        if alpha3 not in LANGUAGES:
            continue
        if alpha3 == "por" and country == _BRAZIL_COUNTRY:
            plan = {"alpha3": "por", "slug": _BRAZIL_SLUG, "country": _BRAZIL_COUNTRY}
        else:
            plan = {"alpha3": alpha3, "slug": LANGUAGES[alpha3]["slug"], "country": None}
        key = (plan["alpha3"], plan["slug"], plan["country"] or "")
        if key in seen:
            continue
        seen.add(key)
        plans.append(plan)
    return plans


def _row_matches_plan(row, plan):
    if row.get("language") != plan["alpha3"]:
        return False
    is_brazil_row = row.get("language_slug") == _BRAZIL_SLUG
    wants_brazil = plan.get("country") == _BRAZIL_COUNTRY
    return is_brazil_row == wants_brazil


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _looks_hearing_impaired(row):
    text = f"{row.get('release_info', '')} {row.get('comment', '')}".lower()
    return (
        re.search(r"\b(?:sdh|hi)\b", text) is not None
        or "hearing impaired" in text
    )


def _year_from_title(title):
    match = _YEAR_RE.search(title or "")
    return int(match.group(1)) if match else None


def _int_from_text(text):
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_html(body):
    sample = (body or b"").lstrip()[:512].lower()
    return sample.startswith((b"<!doctype html", b"<html")) or b"<title" in sample


def _absolute_url(path):
    return urllib.parse.urljoin(BASE_URL + "/", path)


def _strip_tags(value):
    stripped = _TAG_RE.sub(b"", value or b"")
    stripped = _WS_BYTES_RE.sub(b" ", stripped).strip()
    return _WS_RE.sub(" ", html.unescape(_decode(stripped)).replace("\xa0", " ")).strip()


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


def _slug(value):
    return "-".join(_tokens(value)) or "release"


def _decode(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")
