"""API-fetch + response-parsing mixin for OpenSubtitlesProvider.

Extracted from providers/opensubtitles.py. Owns the single ``/subtitles``
request + JSON → SubtitleResult translation, including:

- HTTP status handling (401/403 → ProviderAuthError, 429 →
  ProviderRateLimitError, other → empty list)
- per-item filtering by ``forced_only``
- format detection via filename extension / API ``format`` field
- match-set population for downstream scoring
- uploader trust-bonus lookup
- path-traversal guard via ``secure_filename``

Call sites still live in ``OpenSubtitlesProvider.search`` — the mixin
only surfaces the one public method ``_fetch_and_parse`` plus whatever
state it reads through ``self`` (``session``, ``name``).
"""

import logging
import os

from werkzeug.utils import secure_filename as _secure_filename

from providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleResult,
    VideoQuery,
)
from providers.opensubtitles_helpers import _FORMAT_MAP, _UPLOADER_RANK_BONUS, API_BASE

logger = logging.getLogger(__name__)


class _OpenSubtitlesFetchMixin:
    """Single-request search + result parsing for OpenSubtitlesProvider."""

    def _fetch_and_parse(self, params: dict, query: VideoQuery) -> list[SubtitleResult]:
        """Execute one OpenSubtitles /subtitles request and parse the response into results."""
        results: list[SubtitleResult] = []
        try:
            resp = self.session.get(f"{API_BASE}/subtitles", params=params)
            logger.debug("OpenSubtitles: API response status: %d", resp.status_code)

            if resp.status_code in (401, 403):
                error_msg = f"OpenSubtitles authentication failed: HTTP {resp.status_code}"
                logger.error(error_msg)
                raise ProviderAuthError(error_msg)

            if resp.status_code == 429:
                error_msg = f"OpenSubtitles rate limit exceeded: HTTP {resp.status_code}"
                logger.warning(error_msg)
                raise ProviderRateLimitError(error_msg)

            if resp.status_code != 200:
                logger.warning(
                    "OpenSubtitles search failed: HTTP %d, response: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            data = resp.json()
            logger.debug("OpenSubtitles: API returned %d items", len(data.get("data", [])))
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                files = attrs.get("files", [])
                lang = attrs.get("language", "")
                release = attrs.get("release", "")
                hi = attrs.get("hearing_impaired", False)
                fps = attrs.get("fps", 0)
                feature = attrs.get("feature_details", {})

                uploader_info = attrs.get("uploader", {}) or {}
                uploader_name = uploader_info.get("name", "") or ""
                uploader_rank = (uploader_info.get("rank", "") or "").lower()
                uploader_trust = _UPLOADER_RANK_BONUS.get(uploader_rank, 0.0)

                is_forced = bool(attrs.get("foreign_parts_only", False))
                if query.forced_only and not is_forced:
                    continue
                if not query.forced_only and is_forced:
                    continue

                for f in files:
                    file_id = f.get("file_id")
                    # P2: Sanitize provider-returned filename to prevent path traversal
                    filename = _secure_filename(f.get("file_name", ""))

                    fmt = SubtitleFormat.UNKNOWN
                    ext = os.path.splitext(filename)[1].lower().lstrip(".")
                    if ext in _FORMAT_MAP:
                        fmt = _FORMAT_MAP[ext]
                    if fmt == SubtitleFormat.UNKNOWN:
                        api_fmt = attrs.get("format", "").lower()
                        fmt = _FORMAT_MAP.get(api_fmt, SubtitleFormat.UNKNOWN)

                    matches = set()
                    if params.get("moviehash") and attrs.get("moviehash_match"):
                        matches.add("hash")
                    if query.is_episode:
                        feat_season = feature.get("season_number")
                        feat_episode = feature.get("episode_number")
                        if feat_season == query.season:
                            matches.add("season")
                        if feat_episode == query.episode:
                            matches.add("episode")
                        # Season-1 collapse fallback: credit "episode" match when the
                        # API response episode number equals our absolute episode (covers
                        # edge cases where AniDB absolute happens to match OS episode).
                        if (
                            query.absolute_episode is not None
                            and feat_episode == query.absolute_episode
                        ):
                            matches.add("episode")
                        if (
                            query.series_title
                            and query.series_title.lower()
                            in (feature.get("title", "") or "").lower()
                        ):
                            matches.add("series")
                    else:
                        if (
                            query.title
                            and query.title.lower() in (feature.get("title", "") or "").lower()
                        ):
                            matches.add("title")
                    if query.year and feature.get("year") == query.year:
                        matches.add("year")
                    if query.release_group and query.release_group.lower() in release.lower():
                        matches.add("release_group")

                    results.append(
                        SubtitleResult(
                            provider_name=self.name,
                            subtitle_id=str(file_id),
                            language=lang,
                            format=fmt,
                            filename=filename,
                            release_info=release,
                            hearing_impaired=hi,
                            forced=is_forced,
                            fps=fps if fps else None,
                            matches=matches,
                            provider_data={"file_id": file_id, "foreign_parts_only": is_forced},
                            uploader_name=uploader_name,
                            uploader_trust=uploader_trust,
                        )
                    )

        except (ProviderAuthError, ProviderRateLimitError):
            raise
        except Exception as e:
            logger.error("OpenSubtitles search error: %s", e, exc_info=True)

        return results
