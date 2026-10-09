"""Karagarga provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.cookies import SimpleCookie

PROVIDER_ID = "karagarga"
BASE_URL = "https://karagarga.in"
FORUM_URL = "https://forum.karagarga.in"
DEFAULT_USER_AGENT = "BazarrProviderHub/1.0"
HTTP_TIMEOUT_SECONDS = 30
_DEFAULT_AUTH_KEY = "880ea6a14ea49e853634fbdc5015a024"


class HttpResponse:
    def __init__(self, status, body, headers):
        self.status = int(status)
        self.body = body or b""
        self.headers = headers or {}


class KaragargaProvider:
    def __init__(self):
        self._authenticated = False
        self._tracker_cookies = {}
        self._forum_cookies = {}

    def search(self, video, languages, config):
        video = video or {}
        if video.get("kind") != "movie":
            return []
        if not _wants_plain_english(languages):
            return []
        config = dict(config or {})
        self._ensure_authenticated(config)
        response = self._http_get(
            f"{BASE_URL}/pots.php",
            self._headers(),
            dict(self._tracker_cookies),
            timeout=HTTP_TIMEOUT_SECONDS,
            params={"search": video.get("title") or "", "status": "completed"},
            allow_redirects=False,
        )
        _raise_for_status(response, "Karagarga movie search")
        if _looks_like_login_html(response):
            raise PermissionError("Karagarga request redirected to login")
        subtitles = []
        scans = 0
        for forum_url in parse_search_page(response.body, video.get("year")):
            if scans >= 3:
                break
            subtitles.extend(self._parse_forum(forum_url))
            scans += 1
        if not subtitles:
            return []
        subtitles.sort(key=lambda item: item["downloads"], reverse=True)
        return [_candidate(subtitles[0], video)]

    def download(self, provider_payload, language, config):
        del language
        payload = dict(provider_payload or {})
        page_url = payload.get("page_url")
        if not page_url:
            raise ValueError("karagarga download requires page_url")
        if _allowed_origin(page_url) != "forum.karagarga.in":
            raise ValueError("Karagarga attachment URL must use the forum origin")
        config = dict(config or {})
        self._ensure_authenticated(config)
        response = self._http_get(
            page_url, self._headers(), dict(self._forum_cookies),
            timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=False,
        )
        _raise_for_status(response, "Karagarga download")
        if _looks_like_login_html(response):
            raise PermissionError("Karagarga request redirected to login")
        body = response.body
        if not body or not body.strip():
            raise ValueError("karagarga downloaded empty subtitle")
        if _is_archive_body(body):
            return _archive_payload(body)
        if _looks_like_binary_or_html(body):
            raise ValueError("Karagarga attachment is not a subtitle")
        if not _is_utf16_bom(body):
            body = _normalize_line_endings(body)
        fmt = _format_from_filename(payload.get("filename") or page_url) or _format_from_content(body)
        if not fmt:
            raise ValueError("Karagarga attachment format is unrecognized")
        return _content_payload(body, fmt)

    def _parse_forum(self, forum_url):
        if _allowed_origin(forum_url) != "forum.karagarga.in":
            raise ValueError("Karagarga forum URL must use the forum origin")
        response = self._http_get(
            forum_url, self._headers(), dict(self._forum_cookies),
            timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=False,
        )
        _raise_for_status(response, "Karagarga forum scan")
        if _looks_like_login_html(response):
            raise PermissionError("Karagarga request redirected to login")
        return parse_forum_page(response.body)

    def _ensure_authenticated(self, config):
        if self._authenticated:
            return
        username = str(config.get("username") or "").strip()
        password = str(config.get("password") or "")
        if not username or not password:
            raise PermissionError("Karagarga requires username and password")
        main_response = self._http_post(
            f"{BASE_URL}/takelogin.php",
            {"username": username, "password": password},
            self._headers(),
            dict(self._tracker_cookies),
            timeout=HTTP_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        _raise_for_login_status(main_response, "Karagarga tracker login")
        _store_response_cookies(self._tracker_cookies, main_response)
        if "pass" not in self._tracker_cookies:
            raise PermissionError("Karagarga tracker username or password is invalid")
        forum_username = str(config.get("f_username") or username).strip()
        forum_password = str(config.get("f_password") or password)
        auth_key = self._forum_auth_key()
        forum_response = self._http_post(
            f"{FORUM_URL}/index.php",
            {
                "auth_key": auth_key,
                "referer": f"{FORUM_URL}/",
                "ips_username": forum_username,
                "ips_password": forum_password,
                "rememberMe": "1",
                "anonymous": "1",
            },
            self._headers(),
            dict(self._forum_cookies),
            timeout=HTTP_TIMEOUT_SECONDS,
            allow_redirects=False,
            params={
                "app": "core",
                "module": "global",
                "section": "login",
                "do": "process",
            },
        )
        _raise_for_login_status(forum_response, "Karagarga forum login")
        _store_response_cookies(self._forum_cookies, forum_response)
        if not {"session_id", "pass_hash"}.issubset(self._forum_cookies):
            raise PermissionError("Karagarga forum username or password is invalid")
        self._authenticated = True
        return

    def _forum_auth_key(self):
        response = self._http_get(
            f"{FORUM_URL}/index.php",
            self._headers(),
            dict(self._forum_cookies),
            timeout=HTTP_TIMEOUT_SECONDS,
            allow_redirects=False,
            params={"app": "core", "module": "global", "section": "login"},
        )
        _raise_for_login_status(response, "Karagarga forum login page")
        _store_response_cookies(self._forum_cookies, response)
        return _parse_auth_key(response.body) or _DEFAULT_AUTH_KEY

    def _headers(self):
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": DEFAULT_USER_AGENT,
        }

    def _http_get(self, url, headers, cookies, timeout=HTTP_TIMEOUT_SECONDS, params=None, allow_redirects=True):
        return _http_request(
            "GET",
            url,
            headers,
            cookies,
            timeout=timeout,
            params=params,
            allow_redirects=allow_redirects,
        )

    def _http_post(
        self,
        url,
        data,
        headers,
        cookies,
        timeout=HTTP_TIMEOUT_SECONDS,
        params=None,
        allow_redirects=True,
    ):
        return _http_request(
            "POST",
            url,
            headers,
            cookies,
            data=data,
            timeout=timeout,
            params=params,
            allow_redirects=allow_redirects,
        )


def _http_request(
    method,
    url,
    headers,
    cookies,
    data=None,
    timeout=HTTP_TIMEOUT_SECONDS,
    params=None,
    allow_redirects=True,
):
    origin = _allowed_origin(url)
    if params:
        delimiter = "&" if urllib.parse.urlsplit(url).query else "?"
        url = f"{url}{delimiter}{urllib.parse.urlencode(params)}"
    request_headers = dict(headers or {})
    if cookies:
        request_headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    opener = urllib.request.build_opener(_ScopedRedirectHandler(origin) if allow_redirects else _NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResponse(response.status, response.read(), response.headers)
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read(), exc.headers)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Karagarga request failed: {exc.reason}") from exc


def _allowed_origin(url):
    if not isinstance(url, str) or not url or url != url.strip():
        raise ValueError("Invalid Karagarga URL")
    if "\\" in url or any(ord(char) < 32 for char in url):
        raise ValueError("Invalid Karagarga URL")
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid Karagarga URL") from exc
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.hostname not in {"karagarga.in", "forum.karagarga.in"}
    ):
        raise ValueError("Karagarga URL must use a known HTTPS origin")
    return parts.hostname


class _ScopedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin):
        self._origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _allowed_origin(newurl) != self._origin:
            raise ValueError("Karagarga redirect changed origin")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _raise_for_status(response, context):
    if response.status == 302:
        raise PermissionError("Karagarga request redirected to login")
    if response.status >= 400:
        raise RuntimeError(f"{context} failed with HTTP {response.status}")


def _raise_for_login_status(response, context):
    if response.status >= 400:
        raise RuntimeError(f"{context} failed with HTTP {response.status}")


def parse_search_page(body, year):
    root = _parse_html(body)
    forum_urls = []
    for table in root.descendants("table"):
        if table.attrs.get("cellspacing") != "5":
            continue
        for row in table.descendants("tr"):
            cells = row.direct_children("td")
            if len(cells) != 11:
                continue
            if "forum.karagarga" not in row.html_hint():
                continue
            title = cells[1].text()
            if year and f"({year}" not in title:
                continue
            if "english" not in cells[5].text().lower():
                continue
            forum_item = cells[9]
            if "approved" not in forum_item.html_hint().lower():
                continue
            link = forum_item.first_link()
            if link:
                url = urllib.parse.urljoin(f"{FORUM_URL}/", link)
                if _is_forum_url(url):
                    forum_urls.append(url)
    return forum_urls


def _is_forum_url(url):
    try:
        return _allowed_origin(url) == "forum.karagarga.in"
    except ValueError:
        return False


def _parse_auth_key(body):
    root = _parse_html(body)
    for node in root.descendants("input"):
        if node.attrs.get("name") == "auth_key":
            value = node.attrs.get("value")
            if value:
                return value
    return ""


def parse_forum_page(body):
    root = _parse_html(body)
    subtitles = []
    seen = set()
    for post in root.descendants("div"):
        classes = set(post.classes())
        if not {"post", "entry-content"}.issubset(classes):
            continue
        for potential in post.descendants_any({"p", "li", "div"}):
            downloads = potential.first_descendant("span", {"desc", "lighter"})
            if downloads is None:
                continue
            try:
                download_count = int(downloads.text().split()[0])
            except (IndexError, ValueError):
                continue
            item = potential.first_link_with_strong()
            if item is None:
                continue
            href = item.attrs.get("href")
            if not href:
                continue
            url = urllib.parse.urljoin(f"{FORUM_URL}/", href)
            if not _is_forum_url(url) or url in seen:
                continue
            strong = item.first_descendant("strong")
            release_info = strong.text() if strong is not None else ""
            if not release_info:
                continue
            seen.add(url)
            attachment_format = _attachment_format(item.text(), href)
            subtitles.append(
                {
                    "page_url": url,
                    "attachment_format": attachment_format,
                    "release_info": release_info,
                    "downloads": download_count,
                    "language": {"alpha3": "eng", "hi": False, "forced": False},
                }
            )
    return subtitles


def _attachment_format(text, href):
    for source in (text, href):
        match = re.search(r"\.(srt|ass|ssa|vtt|sub)\b", str(source or ""), re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def _candidate(item, video):
    matches = ["title", "year"]
    release_group = _clean_key(video.get("release_group") or "")
    if release_group and release_group in _clean_key(item.get("release_info") or ""):
        matches.append("release_group")
    score = min(100, 25 * len(matches))
    attachment_format = item.get("attachment_format")
    filename = _clean_filename(item["release_info"]) + ("." + attachment_format if attachment_format else "")
    return {
        "provider": PROVIDER_ID,
        "id": item["page_url"],
        "language": item["language"],
        "release_info": item["release_info"],
        "filename": filename,
        "matches": matches,
        "score": score,
        "score_without_hash": score,
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "page_link": item["page_url"],
        "display": {
            "source": "karagarga.in",
            "release": item["release_info"],
            "downloads": item["downloads"],
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "page_url": item["page_url"],
            "release_info": item["release_info"],
            "filename": filename,
            "downloads": item["downloads"],
        },
    }


class _Node:
    def __init__(self, tag="", attrs=None):
        self.tag = tag
        self.attrs = {key: value for key, value in (attrs or [])}
        self.children = []
        self.data = []

    def append(self, child):
        self.children.append(child)

    def classes(self):
        return str(self.attrs.get("class") or "").split()

    def text(self):
        parts = list(self.data)
        for child in self.children:
            parts.append(child.text())
        return " ".join(" ".join(parts).split())

    def html_hint(self):
        values = [self.tag, " ".join(f"{key}={value}" for key, value in self.attrs.items()), self.text()]
        for child in self.children:
            values.append(child.html_hint())
        return " ".join(values)

    def direct_children(self, tag):
        return [child for child in self.children if child.tag == tag]

    def descendants(self, tag):
        found = []
        for child in self.children:
            if child.tag == tag:
                found.append(child)
            found.extend(child.descendants(tag))
        return found

    def descendants_any(self, tags):
        found = []
        for child in self.children:
            if child.tag in tags:
                found.append(child)
            found.extend(child.descendants_any(tags))
        return found

    def first_descendant(self, tag, classes=None):
        wanted = set(classes or [])
        for child in self.children:
            if child.tag == tag and wanted.issubset(set(child.classes())):
                return child
            found = child.first_descendant(tag, wanted)
            if found is not None:
                return found
        return None

    def first_link(self):
        links = self.descendants("a")
        return links[0].attrs.get("href") if links else None

    def first_link_with_strong(self):
        for link in self.descendants("a"):
            if link.first_descendant("strong") is not None:
                return link
        return None


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
        text = html.unescape(data).strip()
        if text:
            self.stack[-1].data.append(text)


def _parse_html(body):
    parser = _TreeBuilder()
    parser.feed((body or b"").decode("iso-8859-1", "ignore") if isinstance(body, bytes) else str(body or ""))
    return parser.root


def _store_response_cookies(target, response):
    for header in _header_values(response.headers, "set-cookie"):
        if not header:
            continue
        for fragment in _split_set_cookie(header):
            cookie = SimpleCookie()
            try:
                cookie.load(fragment)
            except Exception:
                continue
            for key, morsel in cookie.items():
                target[key] = morsel.value


def _header_values(headers, name):
    wanted = name.lower()
    if hasattr(headers, "get_all"):
        return [str(value) for value in headers.get_all(name) or headers.get_all(wanted) or []]
    if isinstance(headers, (list, tuple)):
        return [str(value) for key, value in headers if str(key).lower() == wanted]
    value = _header(headers, name)
    return [value] if value else []


_LOGIN_MARKERS = (
    "section=login",
    "takelogin.php",
    "ips_username",
)


def _looks_like_login_html(response):
    sample = (response.body or b"").decode("utf-8", errors="ignore").lower()
    return any(marker in sample for marker in _LOGIN_MARKERS)


def _split_set_cookie(header):
    parts = re.split(r",\s*(?=[A-Za-z0-9_]+=)", str(header))
    return [part.strip() for part in parts if part.strip()]


def _requested_languages(languages):
    return {str(item.get("alpha3")) for item in languages or [] if isinstance(item, dict) and item.get("alpha3")}


def _wants_plain_english(languages):
    for item in languages or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("alpha3")) != "eng":
            continue
        if not item.get("hi") and not item.get("forced"):
            return True
    return False


def _header(headers, name):
    wanted = name.lower()
    if hasattr(headers, "get"):
        value = headers.get(name) or headers.get(wanted)
        if value is not None:
            return str(value)
    if isinstance(headers, (list, tuple)):
        for key, value in headers:
            if str(key).lower() == wanted:
                return str(value)
        return ""
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _clean_key(value):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _clean_filename(value):
    text = re.sub(r"[^A-Za-z0-9]+", ".", str(value or "")).strip(".")
    return text or "karagarga"


def _format_from_filename(filename):
    lower = urllib.parse.urlparse(str(filename or "")).path.lower()
    for extension in (".srt", ".ass", ".ssa", ".vtt", ".sub"):
        if lower.endswith(extension):
            return extension.lstrip(".")
    return None


def _normalize_line_endings(body):
    return body.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _is_archive_body(body):
    return body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"))


def _archive_payload(body):
    return {
        "archive_b64": base64.b64encode(body).decode("ascii"),
        "archive_sha256": hashlib.sha256(body).hexdigest(),
    }


def _is_utf16_bom(body):
    return body.startswith((b"\xff\xfe", b"\xfe\xff"))


def _looks_like_binary_or_html(body):
    if _is_utf16_bom(body):
        try:
            decoded = body.decode("utf-16")
        except UnicodeDecodeError:
            return True
        sample = decoded[:4096].lstrip().lower()
        if sample.startswith(("<html", "<!doctype html", "<body", "<form", "<?xml")):
            return True
        return any(ord(char) < 32 and char not in "\t\n\r" for char in decoded[:4096])
    sample = body[:4096].lstrip().lower()
    if sample.startswith((b"<html", b"<!doctype html", b"<body", b"<form", b"<?xml")):
        return True
    return any(byte < 32 and byte not in (9, 10, 13) for byte in body[:4096])


def _format_from_content(body):
    if _is_utf16_bom(body):
        sample = body.decode("utf-16")[:4096].encode("utf-8")
    else:
        sample = body[:4096]
    sample = sample.lstrip(b"\xef\xbb\xbf \t\r\n")
    if sample.startswith(b"WEBVTT"):
        return "vtt"
    if sample.startswith((b"[Script Info]", b"[Events]")):
        return "ass"
    if re.search(rb"(?m)^\s*\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,.]\d+\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d+", sample):
        return "srt"
    if re.search(rb"(?m)^\s*\{\d+\}\{\d+\}", sample):
        return "sub"
    return None


def _content_payload(body, fmt):
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
