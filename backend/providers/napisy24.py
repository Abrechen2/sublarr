"""Napisy24 subtitle provider -- hash-based POST API for Polish subtitles.

Napisy24.pl is a Polish subtitle database that uses file hash matching
for accurate subtitle identification. Subtitles are searched by computing
an MD5 hash of the first 10MB of the media file and posting it to the
CheckSubAgent API endpoint.

API: http://napisy24.pl/run/CheckSubAgent.php
License: GPL-3.0
"""

import hashlib
import io
import logging
import os
import zipfile

from providers import register_provider
from providers.base import (
    ProviderError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

API_URL = "http://napisy24.pl/run/CheckSubAgent.php"

# Size of the chunk to hash (10MB)
HASH_CHUNK_SIZE = 10 * 1024 * 1024


def _compute_napisy24_hash(file_path: str) -> str | None:
    """Compute the Napisy24 file hash (MD5 of first 10MB).

    Based on Bazarr's implementation of the Napisy24 hash algorithm.

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


@register_provider
class Napisy24Provider(SubtitleProvider):
    """Napisy24 subtitle provider -- hash-based POST API for Polish subtitles."""

    name = "napisy24"
    languages = {"pl"}

    # Plugin system attributes
    config_fields = [
        {
            "key": "username",
            "label": "Username",
            "type": "text",
            "required": False,
            "default": "subliminal",
        },
        {
            "key": "password",
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
                    "fh": "d41d8cd98f00b204e9800998ecf8427e",  # MD5 of empty
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

        # Compute file hash
        file_hash = _compute_napisy24_hash(query.file_path)
        if not file_hash:
            logger.warning("Napisy24: failed to compute file hash")
            return []

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

        try:
            resp = self.session.post(
                API_URL,
                data={
                    "postAction": "CheckSub",
                    "ua": self.username,
                    "ap": self.password,
                    "fs": str(file_size),
                    "fh": file_hash,
                    "fn": filename,
                },
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                logger.warning("Napisy24: API returned HTTP %d", resp.status_code)
                return []

            return self._parse_response(resp.text, file_hash)

        except Exception as e:
            logger.warning("Napisy24: search failed: %s", e)
            return []

    def _parse_response(self, response_text: str, file_hash: str) -> list[SubtitleResult]:
        """Parse the pipe-delimited response from Napisy24 API.

        The response format is pipe-delimited. If a subtitle is found,
        the response starts with "OK" and contains subtitle info.
        """
        results = []

        if not response_text:
            logger.debug("Napisy24: empty response")
            return []

        response_text = response_text.strip()

        # Check if response indicates success
        if not response_text.startswith("OK"):
            logger.debug("Napisy24: no subtitle found (response: %s)", response_text[:100])
            return []

        # Parse pipe-delimited response
        # Format: OK|subtitle_id|download_url|... (varies)
        parts = response_text.split("|")
        if len(parts) < 3:
            logger.debug("Napisy24: unexpected response format: %s", response_text[:100])
            return []

        # Extract subtitle info
        subtitle_id = parts[1] if len(parts) > 1 else file_hash
        download_info = parts[2] if len(parts) > 2 else ""

        # Build download URL
        if download_info.startswith("http"):
            download_url = download_info
        elif download_info:
            download_url = (
                f"http://napisy24.pl/run/CheckSubAgent.php?mode=download&id={download_info}"
            )
        else:
            download_url = (
                f"http://napisy24.pl/run/CheckSubAgent.php?mode=download&id={subtitle_id}"
            )

        result = SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"napisy24:{subtitle_id}",
            language="pl",
            format=SubtitleFormat.SRT,
            filename=f"{subtitle_id}.srt",
            download_url=download_url,
            matches={"hash"},  # Hash match = highest score
            provider_data={
                "file_hash": file_hash,
                "raw_response": response_text[:200],
            },
        )
        results.append(result)

        logger.info("Napisy24: found %d subtitle result(s)", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise ProviderError("Napisy24 not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                raise ProviderError(f"Napisy24 download failed: HTTP {resp.status_code}")
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Napisy24 download error: {e}") from e

        content = resp.content

        # Handle ZIP archives: extract first .srt file
        if content[:4] == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        ext = os.path.splitext(name)[1].lower()
                        if ext == ".srt":
                            content = zf.read(name)
                            result.filename = os.path.basename(name)
                            result.format = SubtitleFormat.SRT
                            break
                    else:
                        # No .srt found, try any subtitle file
                        for name in zf.namelist():
                            ext = os.path.splitext(name)[1].lower()
                            if ext in {".ass", ".ssa", ".sub", ".txt"}:
                                content = zf.read(name)
                                result.filename = os.path.basename(name)
                                if ext == ".ass":
                                    result.format = SubtitleFormat.ASS
                                elif ext == ".ssa":
                                    result.format = SubtitleFormat.SSA
                                break
            except zipfile.BadZipFile:
                logger.debug("Napisy24: content is not a valid ZIP, using as-is")

        result.content = content
        logger.info("Napisy24: downloaded %s (%d bytes)", result.filename, len(content))
        return content
