"""CinemaZ provider for the Bazarr+ Provider Hub catalog."""

import base64
import email.message
import hashlib
import html
import io
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from http.cookies import SimpleCookie

PROVIDER_ID = "cinemaz"
BASE_URL = "https://cinemaz.to/"
RULES_URL = urllib.parse.urljoin(BASE_URL, "rules")
DEFAULT_USER_AGENT = "BazarrProviderHub/1.0"
HTTP_TIMEOUT_SECONDS = 30
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
_SXXEXX_RE = re.compile(r"\bs(?P<season>\d{1,2})\s*[._ -]?e(?P<episode>\d{1,3})\b", re.I)

LANGUAGE_NAME_TO_ALPHA3 = {
    "abkhazian": "abk",
    "afar": "aar",
    "afrikaans": "afr",
    "akan": "aka",
    "albanian": "sqi",
    "amharic": "amh",
    "arabic": "ara",
    "aragonese": "arg",
    "armenian": "hye",
    "assamese": "asm",
    "avaric": "ava",
    "avestan": "ave",
    "aymara": "aym",
    "azerbaijani": "aze",
    "bambara": "bam",
    "bashkir": "bak",
    "basque": "eus",
    "belarusian": "bel",
    "bengali": "ben",
    "bihari languages": "bih",
    "bislama": "bis",
    "bokmal norwegian": "nor",
    "bokmal, norwegian": "nor",
    "bokmål, norwegian": "nor",
    "bosnian": "bos",
    "brazilian portuguese": "por",
    "breton": "bre",
    "bulgarian": "bul",
    "burmese": "mya",
    "cantonese": "zho",
    "catalan": "cat",
    "central khmer": "khm",
    "chamorro": "cha",
    "chechen": "che",
    "chichewa": "nya",
    "chinese": "zho",
    "church slavic": "chu",
    "chuvash": "chv",
    "cornish": "cor",
    "corsican": "cos",
    "cree": "cre",
    "croatian": "hrv",
    "czech": "ces",
    "danish": "dan",
    "dhivehi": "div",
    "dutch": "nld",
    "dzongkha": "dzo",
    "english": "eng",
    "esperanto": "epo",
    "estonian": "est",
    "ewe": "ewe",
    "faroese": "fao",
    "fijian": "fij",
    "filipino": "fil",
    "finnish": "fin",
    "french": "fra",
    "fulah": "ful",
    "gaelic": "gla",
    "galician": "glg",
    "ganda": "lug",
    "georgian": "kat",
    "german": "deu",
    "greek": "ell",
    "guarani": "grn",
    "gujarati": "guj",
    "haitian": "hat",
    "hausa": "hau",
    "hebrew": "heb",
    "herero": "her",
    "hindi": "hin",
    "hiri motu": "hmo",
    "hungarian": "hun",
    "icelandic": "isl",
    "ido": "ido",
    "igbo": "ibo",
    "indonesian": "ind",
    "interlingua": "ina",
    "interlingue": "ile",
    "inuktitut": "iku",
    "inupiaq": "ipk",
    "irish": "gle",
    "italian": "ita",
    "japanese": "jpn",
    "javanese": "jav",
    "kalaallisut": "kal",
    "kannada": "kan",
    "kanuri": "kau",
    "kashmiri": "kas",
    "kazakh": "kaz",
    "kikuyu": "kik",
    "kinyarwanda": "kin",
    "kirghiz": "kir",
    "komi": "kom",
    "kongo": "kon",
    "korean": "kor",
    "kuanyama": "kua",
    "kurdish": "kur",
    "lao": "lao",
    "latin": "lat",
    "latvian": "lav",
    "limburgan": "lim",
    "lingala": "lin",
    "lithuanian": "lit",
    "luba-katanga": "lub",
    "luxembourgish": "ltz",
    "macedonian": "mkd",
    "malagasy": "mlg",
    "malay": "msa",
    "malayalam": "mal",
    "maltese": "mlt",
    "mandarin": "zho",
    "manx": "glv",
    "maori": "mri",
    "marathi": "mar",
    "marshallese": "mah",
    "mongolian": "mon",
    "moore": "mos",
    "nauru": "nau",
    "navajo": "nav",
    "ndebele north": "nde",
    "ndebele, north": "nde",
    "ndebele south": "nbl",
    "ndebele, south": "nbl",
    "ndonga": "ndo",
    "nepali": "nep",
    "northern sami": "sme",
    "norwegian": "nor",
    "norwegian nynorsk": "nno",
    "occitan": "oci",
    "occitan post 1500": "oci",
    "occitan (post 1500)": "oci",
    "ojibwa": "oji",
    "oriya": "ori",
    "oromo": "orm",
    "ossetian": "oss",
    "pali": "pli",
    "panjabi": "pan",
    "persian": "fas",
    "polish": "pol",
    "portuguese": "por",
    "pushto": "pus",
    "quechua": "que",
    "romanian": "ron",
    "romansh": "roh",
    "rundi": "run",
    "russian": "rus",
    "samoan": "smo",
    "sango": "sag",
    "sanskrit": "san",
    "sardinian": "srd",
    "serbian": "srp",
    "shona": "sna",
    "sichuan yi": "iii",
    "sindhi": "snd",
    "sinhala": "sin",
    "slovak": "slk",
    "slovenian": "slv",
    "somali": "som",
    "sotho southern": "sot",
    "sotho, southern": "sot",
    "spanish": "spa",
    "sundanese": "sun",
    "swahili": "swa",
    "swati": "ssw",
    "swedish": "swe",
    "tagalog": "tgl",
    "tahitian": "tah",
    "tajik": "tgk",
    "tamil": "tam",
    "tatar": "tat",
    "telugu": "tel",
    "thai": "tha",
    "tibetan": "bod",
    "tigrinya": "tir",
    "tongan": "ton",
    "tsonga": "tso",
    "tswana": "tsn",
    "turkish": "tur",
    "turkmen": "tuk",
    "twi": "twi",
    "uighur": "uig",
    "ukrainian": "ukr",
    "urdu": "urd",
    "uzbek": "uzb",
    "venda": "ven",
    "vietnamese": "vie",
    "volapuk": "vol",
    "volapük": "vol",
    "walloon": "wln",
    "welsh": "cym",
    "western frisian": "fry",
    "wolof": "wol",
    "xhosa": "xho",
    "yiddish": "yid",
    "yoruba": "yor",
    "zhuang": "zha",
    "zulu": "zul",
}

# Country variants for language names that map to a base alpha3 but carry a
# region. The catalog advertises only the base alpha3 (for example por), so the
# region is tracked separately as a country code and matched against requests
# that carry a country field such as country_alpha2: BR.
LANGUAGE_NAME_TO_COUNTRY = {
    "brazilian portuguese": "BR",
}


class HttpResponse:
    def __init__(self, status, body, headers):
        self.status = int(status)
        self.body = body or b""
        self.headers = dict(headers or {})


class CinemaZProvider:
    def __init__(self):
        self._cookies_verified = False

    def search(self, video, languages, config):
        config = dict(config or {})
        info_url = str((video or {}).get("info_url") or "")
        if not _is_cinemaz_url(info_url):
            return []
        cookies = _parse_cookies(config)
        requested = _requested_languages(languages)
        if not requested:
            return []
        self._ensure_cookies(cookies, config)
        response = self._http_get(info_url, self._headers(config), cookies, timeout=HTTP_TIMEOUT_SECONDS)
        if response.status == 404:
            return []
        _raise_for_status(response, "CinemaZ release page")
        release = parse_release_page(response.body, info_url)
        results = []
        for subtitle in release["subtitles"]:
            alpha3 = language_alpha3(subtitle["language"])
            if not alpha3:
                continue
            country = language_country(subtitle["language"])
            key = f"{alpha3}-{country}" if country else alpha3
            # A generic request (por) also accepts a regional row (por-BR).
            if (key, False) not in requested and (alpha3, False) not in requested:
                continue
            results.append(_candidate(release, subtitle, alpha3, country, video))
        return results

    def download(self, provider_payload, language, config):
        del language
        config = dict(config or {})
        payload = provider_payload or {}
        download_url = payload.get("download_url")
        if not download_url:
            raise ValueError("cinemaz download requires download_url")
        if not _is_cinemaz_url(download_url):
            raise ValueError("CinemaZ download URL must use HTTPS on cinemaz.to")
        cookies = _parse_cookies(config)
        response = self._http_get(download_url, self._headers(config), cookies, timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=False)
        _raise_for_status(response, "CinemaZ subtitle download")
        if _looks_like_html(response):
            raise PermissionError("CinemaZ subtitle download returned a login page")
        body = response.body or b""
        if not body:
            raise ValueError("cinemaz downloaded empty subtitle")
        if _is_archive_body(body):
            return _archive_payload(body, payload)
        filename = payload.get("filename") or download_url
        subtitle_format = _subtitle_extension(_response_filename(response.headers)) or _format_from_filename(filename)
        body = _normalize_line_endings(body)
        return _content_payload(body, subtitle_format)

    def _ensure_cookies(self, cookies, config):
        if self._cookies_verified:
            return
        headers = self._headers(config)
        headers["Referer"] = BASE_URL
        response = self._http_get(RULES_URL, headers, cookies, timeout=10, allow_redirects=False)
        if response.status in {302, 403, 404}:
            raise PermissionError("CinemaZ cookies are not valid anymore")
        _raise_for_status(response, "CinemaZ cookie validation")
        self._cookies_verified = True

    def _headers(self, config):
        user_agent = str((config or {}).get("user_agent") or "").strip() or DEFAULT_USER_AGENT
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": user_agent,
        }

    def _http_get(self, url, headers, cookies, timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=True):
        if not _is_cinemaz_url(url):
            raise ValueError("CinemaZ request URL must use HTTPS on cinemaz.to")
        request_headers = dict(headers or {})
        if cookies:
            request_headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        if allow_redirects:
            opener = urllib.request.build_opener(_SameOriginRedirectHandler())
        else:
            opener = urllib.request.build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=timeout) as response:
                return HttpResponse(response.status, response.read(), dict(response.headers.items()))
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, exc.read(), dict(exc.headers.items()))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"CinemaZ request failed: {exc.reason}") from exc


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_cinemaz_url(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _parse_cookies(config):
    value = str((config or {}).get("cookies") or "").strip()
    if not value:
        raise ValueError("CinemaZ cookies are required")
    cookie = SimpleCookie()
    cookie.load(value)
    parsed = {key: morsel.value for key, morsel in cookie.items()}
    if not parsed:
        raise ValueError("CinemaZ cookies are required")
    return parsed


def _requested_languages(languages):
    requested = set()
    for item in languages or []:
        if not isinstance(item, dict):
            continue
        # CinemaZ does not parse or mark forced rows, so a forced-only request
        # must be skipped instead of surfacing regular subtitles.
        if item.get("forced"):
            continue
        alpha3 = _language_id(item)
        if not alpha3:
            continue
        requested.add((alpha3, bool(item.get("hi"))))
    return requested


def _language_id(language):
    alpha3 = str(language.get("alpha3") or "").strip()
    country = str(language.get("country") or language.get("country_alpha2") or "").strip().upper()
    if alpha3 and country and "-" not in alpha3:
        return f"{alpha3}-{country}"
    return alpha3


def _is_cinemaz_url(url):
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    if any(ord(character) <= 32 or ord(character) == 127 for character in url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() == "cinemaz.to"
        and parsed.username is None
        and parsed.password is None
        and "@" not in parsed.netloc
        and port in {None, 443}
    )


def _raise_for_status(response, context):
    if 300 <= response.status < 400:
        raise PermissionError(f"{context} redirected to login")
    if response.status >= 400:
        raise RuntimeError(f"{context} failed with HTTP {response.status}")


def language_alpha3(language_name):
    normalized = _normalize_language_name(language_name)
    if len(normalized) == 3 and normalized.isalpha():
        return normalized
    return LANGUAGE_NAME_TO_ALPHA3.get(normalized)


def language_country(language_name):
    normalized = _normalize_language_name(language_name)
    return LANGUAGE_NAME_TO_COUNTRY.get(normalized)


def _normalize_language_name(value):
    text = html.unescape(str(value or "")).strip().lower()
    text = " ".join(text.replace("\xa0", " ").split())
    text = text.replace("(", "").replace(")", "")
    return text


def _candidate(release, subtitle, alpha3, country, video):
    download_url = subtitle["download_url"]
    subtitle_id = _subtitle_id(download_url) or alpha3
    filename = subtitle.get("filename") or download_url.rstrip("/").split("/")[-1] or f"cinemaz-{alpha3}.srt"
    if not _subtitle_extension(filename) and subtitle.get("extension"):
        filename = f"cinemaz-{subtitle_id}.{alpha3}.{subtitle['extension']}"
    release_info = release["title"]
    language = {"alpha3": alpha3, "hi": False, "forced": False}
    if country:
        language["country_alpha2"] = country
    result_id = filename if _subtitle_extension(filename) else f"{subtitle_id}-{filename}"
    candidate_id = f"cinemaz-{result_id}-{alpha3}-{country}" if country else f"cinemaz-{result_id}-{alpha3}"
    matches = _release_matches(release_info, video)
    score = _score(matches)
    return {
        "provider": PROVIDER_ID,
        "id": candidate_id,
        "language": language,
        "release_info": release_info,
        "filename": filename,
        "matches": matches,
        "score": score,
        "score_without_hash": score,
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "page_link": release["page_url"],
        "display": {
            "source": "cinemaz.to",
            "title": release_info,
            "uploader": subtitle.get("uploader"),
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "download_url": download_url,
            "filename": filename,
            "release_info": release_info,
            "page_url": release["page_url"],
            "kind": (video or {}).get("kind"),
            "season": (video or {}).get("season"),
            "episode": (video or {}).get("episode"),
        },
    }


def _release_matches(release_info, video):
    matches = []
    video = video or {}
    release_key = _clean_key(release_info)
    title = video.get("series") if video.get("kind") == "episode" else video.get("title")
    title_key = _clean_key(title)
    if title_key and title_key in release_key:
        matches.append("series" if video.get("kind") == "episode" else "title")
    year = video.get("year")
    if year and str(year) in str(release_info):
        matches.append("year")
    if video.get("kind") == "episode":
        wanted_season = _int_or_none(video.get("season"))
        wanted_episode = _int_or_none(video.get("episode"))
        match = _SXXEXX_RE.search(str(release_info or ""))
        if match and wanted_season is not None and int(match.group("season")) == wanted_season:
            matches.append("season")
            if wanted_episode is not None and int(match.group("episode")) == wanted_episode:
                matches.append("episode")
    release_group = _clean_key(video.get("release_group"))
    if release_group and release_group in release_key:
        matches.append("release_group")
    return matches


def _clean_key(value):
    return " ".join(re.findall(r"[a-z0-9]+", html.unescape(str(value or "")).lower()))


def _score(matches):
    if not matches:
        return 0
    return min(95, 20 * len(matches))


def parse_release_page(body, page_url):
    root = _parse_html(body)
    table = _find_release_table(root)
    if table is None:
        return _parse_unit3d_release_page(root, page_url)
    rows = _release_rows(table)
    title_cell = rows.get("title")
    subtitles_cell = rows.get("subtitles")
    if title_cell is None:
        raise RuntimeError("CinemaZ release page did not include a title row")
    if subtitles_cell is None:
        return {"title": title_cell.text(), "page_url": page_url, "subtitles": []}
    subtitle_table = subtitles_cell.first_descendant("table")
    if subtitle_table is None:
        return {"title": title_cell.text(), "page_url": page_url, "subtitles": []}
    return {
        "title": title_cell.text(),
        "page_url": page_url,
        "subtitles": _subtitle_rows(subtitle_table, page_url),
    }


def _parse_unit3d_release_page(root, page_url):
    title = root.first_descendant("h1")
    if title is None:
        raise RuntimeError("Unexpected CinemaZ release page layout")
    for table in root.descendants("table"):
        subtitles = _subtitle_rows(table, page_url)
        if subtitles:
            return {"title": title.text(), "page_url": page_url, "subtitles": subtitles}
    return {"title": title.text(), "page_url": page_url, "subtitles": []}


def _find_release_table(root):
    for table in root.descendants("table"):
        rows = _release_rows(table)
        if "title" in rows and "subtitles" in rows:
            return table
    return None


def _release_rows(table):
    rows = {}
    tbody = table.first_child("tbody")
    if tbody is None:
        return rows
    for tr in tbody.children_named("tr"):
        cells = tr.children_named("td")
        if len(cells) < 2:
            continue
        label = cells[0].text().strip().lower()
        rows[label] = cells[1]
    return rows


def _subtitle_rows(table, page_url):
    headers = [cell.text().strip().lower() for cell in _header_cells(table)]
    if not headers:
        return []
    rows = []
    tbody = table.first_child("tbody")
    if tbody is None:
        return rows
    for tr in tbody.children_named("tr"):
        cells = tr.children_named("td")
        if len(cells) < len(headers):
            continue
        mapped = {headers[index]: cells[index] for index in range(len(headers))}
        language_cell = mapped.get("language")
        # Current UNIT3D subtitles partials place the download link inside the
        # Actions column rather than a dedicated Download column, so accept the
        # Actions cell as a fallback source for the link.
        download_cell = mapped.get("download") or mapped.get("actions")
        if language_cell is None or download_cell is None:
            continue
        href = _download_href(download_cell)
        if not href:
            continue
        uploader_cell = mapped.get("uploader")
        extension = _extension_from_cell(mapped.get("extension") or mapped.get("format") or mapped.get("type"))
        download_url = urllib.parse.urljoin(page_url, href)
        if not _is_cinemaz_url(download_url):
            continue
        rows.append(
            {
                "language": language_cell.text(),
                "download_url": download_url,
                "uploader": uploader_cell.text() if uploader_cell is not None else None,
                "extension": extension,
            }
        )
    return rows


def _download_href(cell):
    # The Actions column can hold several links (view, report, download), so
    # prefer the subtitle download endpoint and fall back to the first link.
    links = cell.links()
    if not links:
        return None
    for href in links:
        if href.rstrip("/").lower().endswith("/download"):
            return href
    return links[0]


def _extension_from_cell(cell):
    if cell is None:
        return ""
    value = cell.text().strip().lower().lstrip(".")
    return value if f".{value}" in SUBTITLE_EXTENSIONS else ""


def _subtitle_id(download_url):
    parts = [part for part in urllib.parse.urlparse(download_url).path.split("/") if part]
    if "subtitles" in parts:
        index = parts.index("subtitles")
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _header_cells(table):
    thead = table.first_child("thead")
    if thead is not None:
        headers = []
        for tr in thead.children_named("tr"):
            headers.extend(tr.children_named("th"))
        return headers
    first_row = table.first_descendant("tr")
    return first_row.children_named("th") if first_row else []


class _Node:
    def __init__(self, tag="", attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.data = []

    def append(self, child):
        self.children.append(child)

    def text(self):
        parts = list(self.data)
        for child in self.children:
            parts.append(child.text())
        return " ".join(" ".join(parts).split())

    def first_child(self, tag):
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def children_named(self, tag):
        return [child for child in self.children if child.tag == tag]

    def first_descendant(self, tag):
        for child in self.children:
            if child.tag == tag:
                return child
            found = child.first_descendant(tag)
            if found is not None:
                return found
        return None

    def descendants(self, tag):
        found = []
        for child in self.children:
            if child.tag == tag:
                found.append(child)
            found.extend(child.descendants(tag))
        return found

    def first_link(self):
        link = self.first_descendant("a")
        if link is None:
            return None
        return link.attrs.get("href")

    def links(self):
        return [anchor.attrs.get("href") for anchor in self.descendants("a") if anchor.attrs.get("href")]


class _TreeBuilder(HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag.lower(), attrs)
        self.stack[-1].append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        wanted = tag.lower()
        while len(self.stack) > 1:
            node = self.stack.pop()
            if node.tag == wanted:
                return

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.stack[-1].data.append(text)


def _parse_html(body):
    parser = _TreeBuilder()
    parser.feed((body or b"").decode("utf-8", "ignore") if isinstance(body, bytes) else str(body or ""))
    return parser.root


def _is_archive_body(body):
    body = body or b""
    return zipfile.is_zipfile(io.BytesIO(body)) or body.startswith(b"Rar!\x1a\x07")


def _archive_payload(body, provider_payload):
    return {
        "archive_b64": base64.b64encode(body).decode("ascii"),
        "archive_sha256": hashlib.sha256(body).hexdigest(),
        "season": _int_or_none(provider_payload.get("season")),
        "episode": _int_or_none(provider_payload.get("episode")),
    }


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_html(response):
    content_type = str((response.headers or {}).get("content-type") or (response.headers or {}).get("Content-Type") or "").lower()
    sample = (response.body or b"").lstrip()[:2048].decode("utf-8", errors="ignore").lower()
    return "text/html" in content_type or sample.startswith("<!doctype html") or sample.startswith("<html")


def _response_filename(headers):
    for key, value in (headers or {}).items():
        if str(key).lower() == "content-disposition":
            message = email.message.Message()
            message["Content-Disposition"] = str(value)
            return message.get_filename()
    return None


def _subtitle_extension(name):
    lower = str(name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lower.endswith(extension):
            return extension.lstrip(".")
    return None


def _format_from_filename(filename):
    return _subtitle_extension(urllib.parse.urlparse(str(filename)).path) or "srt"


def _normalize_line_endings(body):
    return body.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _content_payload(body, fmt):
    if not body:
        raise ValueError("cinemaz downloaded empty subtitle")
    return {
        "content_b64": base64.b64encode(body).decode("ascii"),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "content_type": _content_type(fmt),
        "format": fmt,
        "empty": False,
    }


def _content_type(fmt):
    if fmt in {"ass", "ssa"}:
        return "text/x-ssa"
    if fmt == "vtt":
        return "text/vtt"
    if fmt == "sub":
        return "text/plain"
    return "application/x-subrip"
