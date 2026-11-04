"""Napisy24 subtitle provider -- hash-based POST API for Polish subtitles.

Napisy24.pl is a Polish subtitle database that matches by file hash. The
search posts the OpenSubtitles hash (``fh``, upper case), the MD5 of the
first 10 MB (``md``, lower case) and the size to CheckSubAgent; the answer
is ``OK-2|field:value|...||`` followed by the subtitle ZIP itself. OK-0,
OK-1 and OK-3 carry no subtitle. Until 1.20.0 the provider sent the MD5 as
``fh``, took every OK-* answer for a hit and built a download URL the API
does not have.

API: http://napisy24.pl/run/CheckSubAgent.php
Docs: https://forum.napisy24.pl/viewtopic.php?t=142
License: GPL-3.0
"""

import hashlib
import logging
import os
from typing import ClassVar

from werkzeug.utils import secure_filename as _secure_filename

from archive_utils import extract_subtitles_from_zip
from providers import register_provider
from providers.base import (
    ProviderError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from providers.opensubtitles_helpers import _compute_opensubtitles_hash

logger = logging.getLogger(__name__)

API_URL = "http://napisy24.pl/run/CheckSubAgent.php"

# Size of the chunk to hash (10MB)
HASH_CHUNK_SIZE = 10 * 1024 * 1024


def _compute_napisy24_hash(file_path: str) -> str | None:
    """MD5 of the first 10 MB, the API's optional ``md`` parameter.

    Args:
        file_path: Path to the media file

    Returns:
        MD5 hex digest of first 10MB, or None if file cannot be read
    """
    try:
        md5 = hashlib.md5(usedforsecurity=False)  # noqa: S324
        with open(file_path, "rb") as f:
            data = f.read(HASH_CHUNK_SIZE)
            md5.update(data)
        return md5.hexdigest()
    except OSError as e:
        logger.warning("Napisy24: failed to compute hash for %s: %s", file_path, e)
        return None


_PRIORITY = {".srt": 0, ".ass": 1, ".ssa": 2, ".vtt": 3}
_FORMATS = {
    ".srt": SubtitleFormat.SRT,
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".vtt": SubtitleFormat.VTT,
}


@register_provider
class Napisy24Provider(SubtitleProvider):
    """Napisy24 subtitle provider -- hash-based POST API for Polish subtitles."""

    name = "napisy24"

    # Polish DB with modest free tier — hash-based queries are cheap so 400/day is fine.
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 40, "day": 400},
    }
    languages = {"pl"}

    # Plugin system attributes
    config_fields = [
        {
            "key": "napisy24_username",
            "label": "Username",
            "type": "text",
            "required": False,
            "default": "subliminal",
        },
        {
            "key": "napisy24_password",
            "label": "Password",
            "type": "password",
            "required": False,
            "default": "lanimilbus",
        },
    ]
    rate_limit = (20, 60)  # conservative: 20 requests per minute
    timeout = 15
    max_retries = 2

    def __init__(self, username: str = "subliminal", password: str = "lanimilbus", **kwargs):
        super().__init__(**kwargs)
        self.username = username or "subliminal"
        self.password = password or "lanimilbus"
        self.session = None

    def initialize(self):
        logger.debug("Napisy24: initializing (username: %s)", self.username)
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=15,
            user_agent="Sublarr/1.0",
        )

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            # Simple POST with dummy data to check if the API is reachable
            resp = self.session.post(
                API_URL,
                data={
                    "postAction": "CheckSub",
                    "ua": self.username,
                    "ap": self.password,
                    "fs": "0",
                    "fh": "0000000000000000",
                    "fn": "health_check.mkv",
                },
                timeout=10,
            )
            # The API should respond (even with no results)
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            logger.warning("Napisy24: cannot search -- session is None")
            return []

        # Only search for Polish subtitles
        if query.languages and "pl" not in query.languages:
            logger.debug(
                "Napisy24: skipping -- 'pl' not in requested languages %s", query.languages
            )
            return []

        # Requires file_path for hash computation
        if not query.file_path:
            logger.debug("Napisy24: no file_path provided, skipping")
            return []

        if not os.path.exists(query.file_path):
            logger.debug("Napisy24: file not found: %s", query.file_path)
            return []

        # The OpenSubtitles hash identifies the file; the MD5 is optional.
        file_hash = (query.file_hash or _compute_opensubtitles_hash(query.file_path) or "").upper()
        if not file_hash:
            logger.warning("Napisy24: failed to compute file hash")
            return []
        md5 = _compute_napisy24_hash(query.file_path) or ""

        # Get file size
        try:
            file_size = os.path.getsize(query.file_path)
        except OSError:
            logger.warning("Napisy24: failed to get file size")
            return []

        filename = os.path.basename(query.file_path)

        logger.debug(
            "Napisy24: searching for hash=%s, size=%d, file=%s",
            file_hash,
            file_size,
            filename,
        )

        request = {"fs": str(file_size), "fh": file_hash, "md": md5.lower(), "fn": filename}
        try:
            return self._check_sub(request)
        except Exception as e:
            logger.warning("Napisy24: search failed: %s", e)
            return []

    def _check_sub(self, request: dict) -> list[SubtitleResult]:
        """POST one CheckSub request; the answer carries the subtitle itself."""
        resp = self.session.post(
            API_URL,
            data={
                "postAction": "CheckSub",
                "ua": self.username,
                "ap": self.password,
                "nl": "pl",
                **request,
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            logger.warning("Napisy24: API returned HTTP %d", resp.status_code)
            return []
        results = self._parse_response(resp.content, request["fh"])
        for result in results:
            result.provider_data["request"] = request  # a cached result has no content
        return results

    def _parse_response(self, raw: bytes, file_hash: str) -> list[SubtitleResult]:
        """The subtitle an ``OK-2`` answer carries after its ``||``; [] for anything else."""
        if not raw or not raw.startswith(b"OK-2"):
            logger.debug("Napisy24: no subtitle (response: %r)", (raw or b"")[:20])
            return []
        meta, _sep, payload = raw.partition(b"||")
        fields = {}
        for part in meta.decode("utf-8", errors="replace").split("|")[1:]:
            key, _colon, value = part.partition(":")
            fields[key.strip()] = value.strip()

        entries = extract_subtitles_from_zip(payload) if payload[:4] == b"PK\x03\x04" else []
        if not entries:
            # The forum reports ZIPs holding only an INFO.txt advert.
            logger.debug("Napisy24: OK-2 without a subtitle file in its ZIP")
            return []
        entries.sort(key=lambda e: _PRIORITY.get(os.path.splitext(e[0])[1].lower(), 99))
        name, content = entries[0]
        ext = os.path.splitext(name)[1].lower()
        napis_id = fields.get("napisId") or ""
        try:
            fps = float(fields["fps"]) if fields.get("fps") else None
        except ValueError:
            fps = None

        return [
            SubtitleResult(
                provider_name=self.name,
                subtitle_id=f"napisy24:{napis_id if napis_id not in ('', '0') else file_hash}",
                language="pl",
                format=_FORMATS.get(ext, SubtitleFormat.SRT),
                # P2: sanitize the archive member name against path traversal
                filename=_secure_filename(name) or "subtitle.srt",
                content=content,
                matches={"hash"},  # Hash match = highest score
                fps=fps,
                provider_data={
                    "file_hash": file_hash,
                    "imdb": fields.get("imdb", ""),
                    "translated_percent": fields.get("tlPrc", ""),
                },
            )
        ]

    def download(self, result: SubtitleResult) -> bytes:
        """The subtitle arrives with the search answer; a cached result asks again."""
        if result.content:
            return result.content
        request = (result.provider_data or {}).get("request")
        if not self.session or not request:
            raise ProviderError("Napisy24 subtitles come with the search; search again")
        fresh = self._check_sub(request)
        if not fresh:
            raise ProviderError("Napisy24 no longer has this subtitle")
        result.content = fresh[0].content
        result.filename = fresh[0].filename
        result.format = fresh[0].format
        return result.content
