"""Run a Bazarr+ Provider Hub bundle as a Sublarr ``SubtitleProvider``.

A bundle is a plain class with ``search(video, languages, config)`` returning
candidate dicts and ``download(payload, language, config)`` returning the
subtitle — the contract documented in the catalog's ``sdk/README.md``. This
module translates both ways: a ``VideoQuery`` into the video dict, candidates
into ``SubtitleResult``, and every download shape (bytes, ``content_b64``,
``archive_b64`` with or without a pinned member) into subtitle bytes.

Scoring stays Sublarr's: a candidate's own ``score`` is ignored and only its
``matches`` are carried over, mapped onto the names ``compute_score`` weighs.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import socket
import urllib.error
from typing import Any, ClassVar

from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.hub.languages import request_payloads, result_language

logger = logging.getLogger(__name__)

_FORMATS = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}
_SCORED_MATCHES = {
    "hash",
    "series",
    "title",
    "year",
    "season",
    "episode",
    "release_group",
    "source",
    "resolution",
    "video_codec",
    "audio_codec",
    "hearing_impaired",
}
# Bundle error classes that mean "slow down" or "your account is the problem".
_RATE_LIMIT_ERRORS = {"RateLimited", "APIThrottled"}
_AUTH_ERRORS = {"AccountLoginFailed", "AccountRequired"}


def config_key(hub_id: str, prop: str) -> str:
    """Where a bundle setting is stored in ``config_entries``."""
    return f"hub.{hub_id}.{prop}"


def video_from_query(query: VideoQuery) -> dict:
    """The video dict a bundle's ``search`` reads, filled from a ``VideoQuery``."""
    path = query.file_path or ""
    video: dict[str, Any] = {
        "kind": "episode" if query.is_episode else "movie",
        "name": path,
        "path": path,
        "original_path": path,
        "original_name": os.path.basename(path),
        "size": query.file_size or None,
        "year": query.year,
        "release_group": query.release_group or None,
        "source": query.source or None,
        "resolution": query.resolution or None,
        "video_codec": query.video_codec or None,
        "hashes": {"opensubtitles": query.file_hash} if query.file_hash else {},
    }
    if query.is_episode:
        video.update(
            {
                "series": query.series_title or query.title,
                "title": query.episode_title or None,
                "season": query.season,
                "episode": query.episode,
                "absolute_episode": query.absolute_episode,
                "alternative_series": [],
                # Sublarr's episode imdb_id is the SERIES id (Sonarr metadata).
                "series_imdb_id": query.imdb_id or None,
                "series_tvdb_id": query.tvdb_id,
                "series_anidb_id": query.anidb_id,
                "series_anidb_episode_id": query.anidb_episode_id,
                "anilist_id": query.anilist_id,
            }
        )
    else:
        video.update(
            {
                "title": query.title,
                "alternative_titles": [],
                "imdb_id": query.imdb_id or None,
                "tmdb_id": query.tmdb_id,
            }
        )
    return video


def scored_matches(raw, kind: str) -> set[str]:
    """Map a candidate's match names onto those Sublarr's scoring weighs.

    An identifier match stands for what it identifies: a series id is the
    series (and its year), an episode's own imdb id is the series, season and
    episode, a movie id is the title and year. Names Sublarr does not score
    (``country``, ``fps``, ``edition``, ...) are dropped.
    """
    names = {str(m) for m in raw or []}
    out = names & _SCORED_MATCHES
    if kind == "episode":
        if names & {"series_imdb_id", "series_tvdb_id", "tvdb_id"}:
            out |= {"series", "year"}
        if "imdb_id" in names:
            out |= {"series", "season", "episode"}
        if "absolute_episode" in names:
            out |= {"season", "episode"}
        out.discard("title")
    else:
        if names & {"imdb_id", "tmdb_id"}:
            out |= {"title", "year"}
        out -= {"series", "season", "episode"}
    return out


def _format_of(name: str) -> SubtitleFormat:
    return _FORMATS.get(os.path.splitext(name or "")[1].lower(), SubtitleFormat.UNKNOWN)


def _coerce(value, schema: dict):
    """A stored setting (always a string in ``config_entries``) as the schema's type."""
    kind = schema.get("type")
    if value is None or value == "":
        return schema.get("default", False if kind == "boolean" else "")
    if kind == "boolean":
        return (
            value
            if isinstance(value, bool)
            else str(value).strip().lower() in {"1", "true", "yes", "on"}
        )
    if kind in ("integer", "number"):
        try:
            return int(value) if kind == "integer" else float(value)
        except (TypeError, ValueError):
            return schema.get("default", 0)
    return str(value)


def translate_error(exc: Exception) -> Exception:
    """A bundle exception as the provider error Sublarr's breaker understands."""
    if isinstance(exc, ProviderError):
        return exc
    name = type(exc).__name__
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            retry = exc.headers.get("Retry-After") if exc.headers else None
            return ProviderRateLimitError(
                str(exc), retry_after=int(retry) if str(retry or "").isdigit() else 60
            )
        if exc.code in (401, 403):
            return ProviderAuthError(str(exc), status_code=exc.code)
        return ProviderError(str(exc))
    if name in _RATE_LIMIT_ERRORS:
        return ProviderRateLimitError(str(exc))
    if name in _AUTH_ERRORS or isinstance(exc, PermissionError):
        return ProviderAuthError(str(exc))
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return ProviderTimeoutError(str(exc))
    return ProviderError(f"{name}: {exc}")


class HubProvider(SubtitleProvider):
    """Base for the classes ``providers.hub`` generates, one per bundle."""

    hub_id: ClassVar[str] = ""
    manifest: ClassVar[dict] = {}
    impl_class: ClassVar[type | None] = None
    # Not part of the implicit "all providers" set: an install that never
    # touched the provider list must not start scraping 40 new sites.
    opt_in: ClassVar[bool] = True
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 120, "day": 1000},
    }

    def __init__(self, **config):
        super().__init__(**config)
        self._impl = None
        # The manager reads ``session is None`` as "not active".
        self.session = None

    # -- lifecycle ---------------------------------------------------------

    def _bundle_config(self) -> dict:
        props = (self.manifest.get("config_schema") or {}).get("properties") or {}
        return {key: _coerce(self.config.get(key), schema) for key, schema in props.items()}

    def _missing_required(self) -> list[str]:
        required = (self.manifest.get("config_schema") or {}).get("required") or []
        return [key for key in required if not str(self.config.get(key) or "").strip()]

    def initialize(self):
        missing = self._missing_required()
        if missing:
            logger.info("%s: not active, missing %s", self.name, ", ".join(missing))
            return
        self._impl = self.impl_class()
        self.session = self._impl

    def terminate(self):
        self._impl = None
        self.session = None

    def health_check(self) -> tuple[bool, str]:
        if self._impl is None:
            return False, "Not initialized"
        return True, "OK"

    # -- search ------------------------------------------------------------

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if self._impl is None:
            return []
        kind = "episode" if query.is_episode else "movie"
        if kind not in (self.manifest.get("supported_media") or ["movie", "episode"]):
            return []
        languages = request_payloads(query.languages)
        if not languages:
            return []
        try:
            candidates = self._impl.search(
                video=video_from_query(query), languages=languages, config=self._bundle_config()
            )
        except Exception as exc:  # noqa: BLE001 — every bundle error maps to a provider error
            raise translate_error(exc) from exc

        results = []
        for candidate in candidates or []:
            result = self._to_result(candidate, query, kind)
            if result is not None:
                results.append(result)
        return results

    def _to_result(self, candidate, query: VideoQuery, kind: str) -> SubtitleResult | None:
        if not isinstance(candidate, dict) or not isinstance(
            candidate.get("provider_payload"), dict
        ):
            return None
        language = result_language(
            candidate.get("language"),
            query.languages,
            hint=f"{candidate.get('filename') or ''} {candidate.get('release_info') or ''}",
        )
        if not language:
            return None
        lang_payload = (
            candidate.get("language") if isinstance(candidate.get("language"), dict) else {}
        )
        display = candidate.get("display") if isinstance(candidate.get("display"), dict) else {}
        filename = str(candidate.get("filename") or "")
        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=str(candidate.get("id") or ""),
            language=language,
            format=_format_of(filename),
            filename=filename,
            release_info=str(candidate.get("release_info") or ""),
            hearing_impaired=bool(candidate.get("hearing_impaired")),
            forced=bool(lang_payload.get("forced")),
            matches=scored_matches(candidate.get("matches"), kind),
            machine_translated=candidate.get("ai_translated") is True,
            uploader_name=str(display.get("uploader") or ""),
            provider_data={
                "payload": candidate["provider_payload"],
                "language": lang_payload or {"alpha3": language},
                "page_link": candidate.get("page_link") or "",
                # What the archive picker needs; download() never sees the query.
                "query": {
                    "season": query.season,
                    "episode": query.episode,
                    "episodes": list(query.episodes or []),
                    "absolute_episode": query.absolute_episode,
                    "series_title": query.series_title,
                },
            },
        )

    # -- download ----------------------------------------------------------

    def download(self, result: SubtitleResult) -> bytes:
        if self._impl is None:
            raise ProviderError(f"{self.name} is not initialized")
        payload = result.provider_data.get("payload") or {}
        language = result.provider_data.get("language") or {}
        config = self._bundle_config()
        try:
            content = self._impl.download(payload, language, config)
        except Exception as exc:  # noqa: BLE001
            raise translate_error(exc) from exc

        name, data = self._unpack(content, result, payload, language, config)
        if not data:
            raise ProviderError(f"{self.name} returned an empty subtitle")
        if name:
            result.filename = os.path.basename(name)
            fmt = _format_of(name)
            if fmt is not SubtitleFormat.UNKNOWN:
                result.format = fmt
        if result.format is SubtitleFormat.UNKNOWN:
            result.format = SubtitleFormat.SRT
        result.content = data
        return data

    def _unpack(self, content, result, payload, language, config) -> tuple[str, bytes]:
        if content is None:
            raise ProviderError(f"{self.name} returned no content")
        if isinstance(content, bytes):
            return result.filename, content
        if isinstance(content, str):
            return result.filename, content.encode("utf-8")
        if not isinstance(content, dict):
            raise ProviderError(f"{self.name} returned {type(content).__name__}")
        if "archive_b64" in content:
            return self._from_archive(content, result, payload, language, config)
        if content.get("empty") is not False or "content_b64" not in content:
            raise ProviderError(f"{self.name} returned no subtitle content")
        data = _b64(content["content_b64"], content.get("content_sha256"), self.name)
        fmt = str(content.get("format") or "").lower()
        name = result.filename
        if fmt and _format_of(name) is SubtitleFormat.UNKNOWN:
            name = f"{os.path.splitext(name or self.name)[0]}.{fmt}"
        return name, data

    def _from_archive(self, content, result, payload, language, config) -> tuple[str, bytes]:
        from archive_utils import (
            _plain_basename,
            extract_subtitles_from_rar,
            extract_subtitles_from_zip,
        )

        raw = _b64(content["archive_b64"], content.get("archive_sha256"), self.name)
        try:
            # Member names keep their own script (Chinese, Greek, Hebrew, ...):
            # secure_filename would reduce "简体.srt" to "srt" and drop it, and
            # the bundles pin members by their real names.
            if raw[:4] == b"PK\x03\x04":
                files = extract_subtitles_from_zip(raw, raw_names=True)
            elif raw[:4] == b"Rar!":
                files = extract_subtitles_from_rar(raw, raw_names=True)
            else:
                raise ProviderError(f"{self.name} returned an archive type Sublarr cannot open")
        except ValueError as exc:  # size limit, compression-ratio guard
            raise ProviderError(f"{self.name} archive refused: {exc}") from exc
        if not files:
            raise ProviderError(f"{self.name} archive holds no subtitle file")

        member = content.get("member")
        if (
            not member
            and content.get("select_member")
            and hasattr(self._impl, "select_archive_member")
        ):
            names = [name for name, _ in files]
            try:
                decision = self._impl.select_archive_member(payload, language, names, config)
            except Exception as exc:  # noqa: BLE001
                raise translate_error(exc) from exc
            if not isinstance(decision, dict):
                decision = {}
            if decision.get("decision") == "reject":
                raise ProviderError(f"{self.name} archive has no file in the wanted language")
            if decision.get("decision") == "pin":
                member = decision.get("member")
        if member:
            wanted = _plain_basename(str(member))
            for name, data in files:
                if name == wanted:
                    return name, data
            raise ProviderError(f"{self.name} archive member {wanted!r} is missing")
        return _pick_member(files, result, self.name)


def _b64(text, expected_sha256, provider_name: str) -> bytes:
    try:
        data = base64.b64decode(str(text).encode("ascii"), validate=True)
    except (ValueError, TypeError) as exc:
        raise ProviderError(f"{provider_name} returned undecodable content") from exc
    if expected_sha256 and hashlib.sha256(data).hexdigest() != str(expected_sha256).lower():
        raise ProviderError(f"{provider_name} content does not match its checksum")
    return data


def _pick_member(files, result: SubtitleResult, provider_name: str) -> tuple[str, bytes]:
    """The archive file for the wanted episode — never an arbitrary one from a pack."""
    from providers.subdl import _pick_best_subtitle

    ctx = result.provider_data.get("query") or {}
    query = VideoQuery(
        series_title=ctx.get("series_title") or "",
        season=ctx.get("season"),
        episode=ctx.get("episode"),
        episodes=list(ctx.get("episodes") or []),
        absolute_episode=ctx.get("absolute_episode"),
    )
    picked = _pick_best_subtitle(files, query, exact_episode=len(files) == 1)
    if picked is None:
        raise ProviderError(f"{provider_name} archive has no file for this episode")
    return picked
