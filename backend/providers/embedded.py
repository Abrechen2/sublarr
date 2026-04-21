"""Embedded subtitle provider — search pipeline integration.

Exposes embedded subtitle tracks from MKV/MP4 video files as subtitle
search results. When an embedded track wins scoring, it is extracted via
ffmpeg instead of downloaded from the internet.

Requires: ffprobe and ffmpeg in PATH (already required by Sublarr core).
Auth:     None required
Rate:     No rate limit (local disk operation)
License:  GPL-3.0
"""

import logging
import os
import tempfile

from ass_probe import is_sdh_stream
from ass_utils import extract_subtitle_stream, get_media_streams
from config import get_settings
from providers import register_provider
from providers.base import (
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)

logger = logging.getLogger(__name__)

# ffprobe language tag → ISO 639-1
# ISO 639-2B/T three-letter codes that ffprobe returns
_LANG3_TO_ISO1 = {
    "eng": "en",
    "ger": "de",
    "deu": "de",
    "fra": "fr",
    "fre": "fr",
    "spa": "es",
    "ita": "it",
    "por": "pt",
    "nld": "nl",
    "dut": "nl",
    "pol": "pl",
    "ron": "ro",
    "rum": "ro",
    "ces": "cs",
    "cze": "cs",
    "slk": "sk",
    "slo": "sk",
    "hun": "hu",
    "hrv": "hr",
    "srp": "sr",
    "bos": "bs",
    "slv": "sl",
    "mkd": "mk",
    "bul": "bg",
    "rus": "ru",
    "ukr": "uk",
    "tur": "tr",
    "ara": "ar",
    "fas": "fa",
    "per": "fa",
    "zho": "zh",
    "chi": "zh",
    "jpn": "ja",
    "kor": "ko",
    "vie": "vi",
    "ind": "id",
    "heb": "he",
    "ell": "el",
    "gre": "el",
    "swe": "sv",
    "dan": "da",
    "nor": "no",
    "fin": "fi",
    "tha": "th",
    "hin": "hi",
    "ben": "bn",
    "msa": "ms",
    "may": "ms",
}

_CODEC_TO_FORMAT = {
    "ass": SubtitleFormat.ASS,
    "ssa": SubtitleFormat.ASS,
    "subrip": SubtitleFormat.SRT,
    "srt": SubtitleFormat.SRT,
    "webvtt": SubtitleFormat.VTT,
    "mov_text": SubtitleFormat.SRT,
    "microdvd": SubtitleFormat.SRT,
}

_CODEC_TO_EXT = {
    "ass": "ass",
    "ssa": "ass",
    "subrip": "srt",
    "srt": "srt",
    "webvtt": "vtt",
    "mov_text": "srt",
    "microdvd": "srt",
}

# Score bonus so embedded tracks beat most internet results when language matches
_EMBEDDED_SCORE_BONUS = 300


def _normalize_lang(tag: str) -> str | None:
    """Convert ffprobe language tag to ISO 639-1. Returns None if unknown."""
    tag = tag.lower().strip()
    if len(tag) == 2:
        return tag  # already ISO 639-1
    return _LANG3_TO_ISO1.get(tag)


@register_provider
class EmbeddedSubtitlesProvider(SubtitleProvider):
    """Embedded subtitle provider.

    Integrates embedded MKV/MP4 subtitle tracks into the automatic search
    pipeline. Tracks are extracted via ffmpeg only when selected as best result.
    No HTTP requests — all operations are local disk reads.
    """

    name = "embedded"
    languages = set(_LANG3_TO_ISO1.values()) | {
        "en",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "nl",
        "pl",
        "ro",
        "cs",
        "sk",
        "hu",
        "hr",
        "sr",
        "bs",
        "sl",
        "mk",
    }
    config_fields: list = []
    rate_limit = (0, 0)  # no rate limit
    timeout = 30
    max_retries = 0

    # Deliberately no self.session — avoids ProviderManager's session=None guard

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._initialized = False

    def initialize(self) -> None:
        self._initialized = True

    def terminate(self) -> None:
        self._initialized = False

    def health_check(self) -> tuple[bool, str]:
        if not self._initialized:
            return False, "Not initialized"
        return True, "OK (local)"

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not query.file_path:
            return []
        if not os.path.exists(query.file_path):
            logger.debug("Embedded: file not on disk: %s", query.file_path)
            return []

        logger.debug("Embedded: probing %s", query.file_path)

        try:
            probe = get_media_streams(query.file_path)
        except Exception as e:
            logger.debug("Embedded: ffprobe failed for %s: %s", query.file_path, e)
            return []

        requested = set(query.languages or [])
        results: list[SubtitleResult] = []
        sub_index = 0

        # 0.71.0 SDH tolerance — read the toggle once per search.
        allow_sdh = True
        sdh_penalty = 5
        try:
            _s = get_settings()
            allow_sdh = bool(getattr(_s, "embedded_allow_sdh", True))
            sdh_penalty = int(getattr(_s, "embedded_sdh_penalty", 5) or 0)
        except Exception:
            logger.debug("Embedded: SDH settings unavailable; using defaults")

        for stream in probe.get("streams", []):
            if stream.get("codec_type") != "subtitle":
                continue

            stream_index = stream.get("index", 0)
            codec = (stream.get("codec_name") or "").lower()
            tags = stream.get("tags") or {}
            disposition = stream.get("disposition") or {}

            lang_tag = tags.get("language") or tags.get("lang") or ""
            iso_lang = _normalize_lang(lang_tag) if lang_tag else None

            if iso_lang is None or (requested and iso_lang not in requested):
                sub_index += 1
                continue

            fmt = _CODEC_TO_FORMAT.get(codec, SubtitleFormat.UNKNOWN)
            ext = _CODEC_TO_EXT.get(codec, "srt")
            forced = bool(disposition.get("forced"))
            title = tags.get("title") or tags.get("handler_name") or ""
            track_name = f"{iso_lang}_{stream_index}.{ext}"

            # 0.71.0 — SDH detection via shared helper (title markers +
            # disposition.hearing_impaired flag). Legacy code checked the
            # title alone; the helper is stricter and more accurate.
            is_hi = is_sdh_stream(stream)
            if is_hi and not allow_sdh:
                # Toggle says SDH is not an acceptable source — skip entirely.
                sub_index += 1
                continue

            # Plan B5 — rank tracks by (language, forced, HI) match.
            # Base bonus applies when language matches (already true here).
            score_bonus = _EMBEDDED_SCORE_BONUS

            # Forced flag preference
            if getattr(query, "forced_only", False):
                score_bonus += 15 if forced else -5

            # HI preference (legacy per-query knob)
            hi_pref = getattr(query, "hi_preference", "include")
            if hi_pref == "prefer" and is_hi:
                score_bonus += 10
            elif hi_pref == "exclude" and is_hi:
                score_bonus -= 999

            # 0.71.0 — small penalty so non-SDH wins ties when both are
            # available. Default 5 points. No effect when the legacy
            # "prefer"/"exclude" knobs above already moved the bonus in
            # a direction the user explicitly asked for.
            if is_hi and hi_pref == "include":
                score_bonus -= sdh_penalty

            results.append(
                SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=f"track_{stream_index}",
                    language=iso_lang,
                    format=fmt,
                    filename=track_name,
                    download_url="",  # no URL — extracted locally
                    release_info=title or f"Embedded track {stream_index}",
                    hearing_impaired=is_hi,
                    forced=forced,
                    matches={"series", "season", "episode"} if query.is_episode else {"title"},
                    provider_data={
                        "file_path": query.file_path,
                        "stream_index": stream_index,
                        "sub_index": sub_index,
                        "codec": codec,
                        "score_bonus": score_bonus,
                    },
                )
            )
            sub_index += 1

        logger.info("Embedded: found %d matching tracks in %s", len(results), query.file_path)
        return results

    def download(self, result: SubtitleResult) -> bytes:
        pd = result.provider_data or {}
        file_path = pd.get("file_path") or ""
        sub_index = pd.get("sub_index", 0)
        codec = pd.get("codec", "srt")

        if not file_path:
            raise RuntimeError("Embedded: no file_path in provider_data")

        ext = _CODEC_TO_EXT.get(codec, "srt")
        stream_info = {"sub_index": sub_index, "format": ext}

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
            os.close(fd)
            extract_subtitle_stream(file_path, stream_info, tmp_path)
            with open(tmp_path, "rb") as fh:
                content = fh.read()
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Embedded: extraction failed: {e}") from e
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        result.content = content
        logger.info("Embedded: extracted %s (%d bytes)", result.filename, len(content))
        return content
