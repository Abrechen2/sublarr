"""Abstract base class for subtitle providers and shared data models.

All providers implement the same interface: search for subtitles matching
a video query and download the best result. Adapted from Bazarr/subliminal
patterns but simplified for Sublarr's focused use case.

License: GPL-3.0 (compatible with Bazarr source)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar


class ProviderError(Exception):
    """Base exception for provider errors (auth, rate-limit, network)."""

    pass


class ProviderAuthError(ProviderError):
    """Authentication or authorization failed."""

    pass


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded.

    ``reset_at`` is the provider-reported moment the allowance returns (aware
    UTC datetime), when the provider exposes one — e.g. OpenSubtitles' daily
    download quota. Consumers that can wait (the subtitle-repair auto-resume)
    schedule themselves from it; ``retry_after`` stays the short-window hint.
    """

    def __init__(self, message: str = "", retry_after: int = 60, reset_at=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.reset_at = reset_at


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""

    pass


class SubtitleFormat(StrEnum):
    ASS = "ass"
    SRT = "srt"
    SSA = "ssa"
    VTT = "vtt"
    UNKNOWN = "unknown"


@dataclass
class VideoQuery:
    """Describes what we're searching for. Built from Sonarr/Radarr metadata."""

    # File info
    file_path: str = ""
    file_size: int = 0
    file_hash: str = ""  # OpenSubtitles hash

    # Common
    title: str = ""
    year: int | None = None
    imdb_id: str = ""  # e.g. "tt1234567"
    tmdb_id: int | None = None  # The Movie Database ID
    genres: list[str] = field(default_factory=list)  # Movie genres

    # Episode-specific
    series_title: str = ""
    season: int | None = None
    episode: int | None = None
    episodes: list[int] = field(default_factory=list)  # all episodes for multi-episode files
    episode_title: str = ""
    is_special: bool = False  # OVA, SP, bonus, etc.
    is_ova: bool = False

    # Anime IDs (for specialized providers)
    anidb_id: int | None = None
    anidb_episode_id: int | None = None
    anilist_id: int | None = None
    tvdb_id: int | None = None

    # Release info (for scoring)
    release_group: str = ""
    source: str = ""  # BluRay, WEB-DL, etc.
    resolution: str = ""  # 1080p, 720p
    video_codec: str = ""  # x264, x265

    # Language preferences
    languages: list[str] = field(default_factory=list)  # ISO 639-1 codes to search for

    # AniDB absolute episode order (set by build_query_from_wanted when series
    # has absolute_order=True and a mapping exists in anidb_absolute_mappings)
    absolute_episode: int | None = None

    # Forced/signs subtitle search
    forced_only: bool = False  # When True, providers filter for forced/signs subtitles

    # HI preference from the language profile — controls scoring bonus/penalty
    hi_preference: str = "include"  # include | prefer | exclude | only

    # Forced scoring preference from the language profile
    forced_scoring: str = "include"  # include | prefer | exclude | only

    # Provider profile from the language profile: names of providers this
    # search may query. Empty = all globally enabled providers.
    allowed_providers: list[str] = field(default_factory=list)

    # Scoring preset name from the language profile (bundled preset, e.g.
    # "Anime"). Empty = global scoring weights from the database.
    scoring_preset: str = ""

    @property
    def is_episode(self) -> bool:
        return self.season is not None and self.episode is not None

    @property
    def is_movie(self) -> bool:
        return not self.is_episode and bool(self.title)

    @property
    def display_name(self) -> str:
        if self.is_episode:
            return f"{self.series_title} S{self.season:02d}E{self.episode:02d}"
        return f"{self.title} ({self.year})" if self.year else self.title


@dataclass
class SubtitleResult:
    """A subtitle found by a provider."""

    # Identity
    provider_name: str
    subtitle_id: str  # Provider-specific ID
    language: str  # ISO 639-1

    # File info
    format: SubtitleFormat = SubtitleFormat.UNKNOWN
    filename: str = ""
    download_url: str = ""

    # Content (populated after download)
    content: bytes | None = field(default=None, repr=False)

    # Matching metadata
    release_info: str = ""
    hearing_impaired: bool = False
    forced: bool = False
    fps: float | None = None

    # Scoring
    score: int = 0
    matches: set[str] = field(default_factory=set)
    score_breakdown: dict = field(default_factory=dict)  # component → points

    # Provider metadata
    provider_data: dict = field(default_factory=dict)

    # Machine-translation detection (populated by providers / MT detector)
    machine_translated: bool = False
    mt_confidence: float = 0.0  # 0-100; 100 = definitely MT

    # Uploader trust (populated by OpenSubtitles provider)
    uploader_name: str = ""
    uploader_trust: float = 0.0  # 0-20 rank-based bonus

    @property
    def is_ass(self) -> bool:
        return self.format in (SubtitleFormat.ASS, SubtitleFormat.SSA)


# ─── Scoring weights (adapted from Bazarr/subliminal) ────────────────────────

EPISODE_SCORES = {
    "hash": 359,
    "series": 180,
    "year": 90,
    "season": 30,
    "episode": 30,
    "release_group": 14,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "video_codec": 2,  # x264/x265/AV1 match
    "hearing_impaired": 1,
    "format_bonus": 50,  # ASS format bonus (Sublarr-specific)
}

MOVIE_SCORES = {
    "hash": 119,
    "title": 60,
    "year": 30,
    "release_group": 13,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "video_codec": 2,  # x264/x265/AV1 match
    "hearing_impaired": 1,
    "format_bonus": 50,
}


# ─── Configurable scoring cache ───────────────────────────────────────────────

import threading as _threading
import time as _time

_SCORING_CACHE_TTL = 60  # seconds

_scoring_cache: dict = {"data": None, "score_type": None, "expires": 0}
_modifier_cache: dict = {"data": {}, "expires": 0}
_scoring_cache_lock = _threading.Lock()


def _get_cached_weights(score_type: str) -> dict:
    """Get merged scoring weights (hardcoded defaults + DB overrides) with caching.

    Uses a 60-second TTL cache. Falls back to hardcoded defaults if the
    database is not available (e.g. during testing).

    Args:
        score_type: 'episode' or 'movie'

    Returns:
        Merged weights dict
    """
    with _scoring_cache_lock:
        now = _time.time()
        if (
            _scoring_cache["data"] is not None
            and _scoring_cache["score_type"] == score_type
            and now < _scoring_cache["expires"]
        ):
            return _scoring_cache["data"]

        defaults = EPISODE_SCORES if score_type == "episode" else MOVIE_SCORES
        db_overrides: dict = {}

        try:
            from db.scoring import get_scoring_weights

            db_overrides = get_scoring_weights(score_type)
        except Exception:
            pass  # DB not initialized or import error — use defaults only

        merged = {**defaults, **db_overrides}
        _scoring_cache["data"] = merged
        _scoring_cache["score_type"] = score_type
        _scoring_cache["expires"] = now + _SCORING_CACHE_TTL
        return merged


def _get_cached_modifier(provider_name: str) -> int:
    """Get per-provider score modifier with caching.

    Uses a 60-second TTL cache. Returns 0 on any exception.

    Args:
        provider_name: Provider name

    Returns:
        Integer modifier (positive = bonus, negative = penalty). 0 if not set.
    """
    with _scoring_cache_lock:
        now = _time.time()
        if now < _modifier_cache["expires"]:
            return _modifier_cache["data"].get(provider_name, 0)

        try:
            from db.scoring import get_all_provider_modifiers

            _modifier_cache["data"] = get_all_provider_modifiers()
        except Exception:
            _modifier_cache["data"] = {}

        _modifier_cache["expires"] = now + _SCORING_CACHE_TTL
        return _modifier_cache["data"].get(provider_name, 0)


def invalidate_scoring_cache() -> None:
    """Clear both scoring caches. Call when config_updated event fires."""
    with _scoring_cache_lock:
        _scoring_cache["data"] = None
        _scoring_cache["score_type"] = None
        _scoring_cache["expires"] = 0
        _modifier_cache["data"] = {}
        _modifier_cache["expires"] = 0


# Bundled presets are static files — cache resolved weight maps for the
# process lifetime, keyed by (preset_name, score_type).
_preset_weights_cache: dict[tuple[str, str], dict] = {}


def _get_preset_weights(preset_name: str, score_type: str) -> dict | None:
    """Resolve a bundled scoring preset to a full weight map.

    Preset weights are merged over the hardcoded defaults so a preset only
    needs to override the keys it cares about. Returns None when the preset
    is unknown or has no weights for this score_type, so the caller can fall
    back to the global DB-backed weights.
    """
    cache_key = (preset_name, score_type)
    if cache_key in _preset_weights_cache:
        return _preset_weights_cache[cache_key]

    resolved: dict | None = None
    try:
        from scoring_presets import get_bundled_preset

        preset = get_bundled_preset(preset_name)
        if preset:
            preset_weights = (preset.get("weights") or {}).get(score_type)
            if isinstance(preset_weights, dict) and preset_weights:
                defaults = EPISODE_SCORES if score_type == "episode" else MOVIE_SCORES
                resolved = {**defaults, **preset_weights}
    except Exception:
        resolved = None  # fall back to global weights

    _preset_weights_cache[cache_key] = resolved
    return resolved


def compute_score(result: SubtitleResult, query: VideoQuery) -> int:
    """Compute match score for a subtitle result against a video query.

    Uses configurable weights from the database (with 60s TTL cache),
    falling back to hardcoded EPISODE_SCORES / MOVIE_SCORES defaults.
    Applies per-provider score modifiers after base score computation.
    Populates result.score_breakdown with per-component point values.
    """
    score_type = "episode" if query.is_episode else "movie"
    # A profile-scoped preset replaces the global weight map for this query
    weights = None
    preset_name = getattr(query, "scoring_preset", "") or ""
    if preset_name:
        weights = _get_preset_weights(preset_name, score_type)
    preset_active = weights is not None
    if weights is None:
        weights = _get_cached_weights(score_type)
    breakdown: dict[str, int] = {}

    for match in result.matches:
        pts = weights.get(match, 0)
        if pts:
            breakdown[match] = pts

    # ASS format bonus (Sublarr always prefers ASS)
    if result.is_ass:
        pts = weights.get("format_bonus", 0)
        if pts:
            breakdown["format_bonus"] = pts

    # Per-provider modifier (bonus or penalty)
    modifier = _get_cached_modifier(result.provider_name)
    if modifier:
        breakdown["provider_modifier"] = int(modifier)

    # Uploader trust bonus (OpenSubtitles only, 0-20 based on uploader rank)
    if result.provider_name == "opensubtitles" and result.uploader_trust > 0:
        breakdown["uploader_trust"] = int(result.uploader_trust)

    # HI preference modifier — use profile value from query, fall back to global settings
    hi_pref = getattr(query, "hi_preference", None)
    if not hi_pref or hi_pref == "include":
        # Only load global settings when the query carries no override
        from config import get_settings  # local import to avoid circular deps

        hi_pref = getattr(get_settings(), "hi_preference", "include")
    if hi_pref == "prefer" and result.hearing_impaired:
        breakdown["hi_preference"] = 30
    elif (
        hi_pref == "exclude"
        and result.hearing_impaired
        or hi_pref == "only"
        and not result.hearing_impaired
    ):
        breakdown["hi_preference"] = -999

    # Forced scoring preference — profile value takes precedence over global setting
    forced_pref = getattr(query, "forced_scoring", None)
    if not forced_pref or forced_pref == "include":
        from config import get_settings as _get_settings

        forced_pref = getattr(_get_settings(), "forced_preference", "include")
    if forced_pref == "prefer" and result.forced:
        breakdown["forced_preference"] = 30
    elif forced_pref == "exclude" and result.forced or forced_pref == "only" and not result.forced:
        breakdown["forced_preference"] = -999

    # Plan B4 — additive penalty rule pipeline. The driver is pure (returns
    # a {rule_id: weight} dict without mutating candidate.score). We merge
    # its entries into the breakdown under ``rule:<id>`` keys before the
    # final sum so pipeline contributions are visible in the UI breakdown
    # and participate in the final score.
    #
    # When a pipeline rule supersedes a legacy weight-map key (e.g.
    # ``release_group_match`` supersedes ``release_group``), drop the legacy
    # credit to avoid double-counting. Disabled rules (weight=0) leave the
    # legacy path untouched.
    try:
        from wanted_search.penalty_rules import (
            apply_penalty_pipeline,
            superseded_legacy_keys,
        )

        pipeline_breakdown = apply_penalty_pipeline(result, query)
        for rule_id, applied in pipeline_breakdown.items():
            breakdown[f"rule:{rule_id}"] = int(applied)
        # When a profile preset is active, the port rules must carry the
        # preset's weight for the legacy key they supersede — otherwise the
        # pipeline would silently swap e.g. the anime preset's format_bonus=80
        # back to the global rule weight. Only positive match bonuses are
        # rewritten; -999 kill switches stay untouched.
        if preset_active:
            from wanted_search.penalty_rules import _RULE_SUPERSEDES

            for rule_id, applied in pipeline_breakdown.items():
                if applied <= 0:
                    continue
                for key in _RULE_SUPERSEDES.get(rule_id, ()):
                    if key in weights:
                        breakdown[f"rule:{rule_id}"] = int(weights[key])
        for legacy_key in superseded_legacy_keys(pipeline_breakdown):
            breakdown.pop(legacy_key, None)
    except Exception:
        # Never let the pipeline break scoring; legacy weight-map path is
        # sufficient on its own.
        pass

    result.score_breakdown = breakdown
    result.score = sum(breakdown.values())
    return result.score


# ─── Provider base class ─────────────────────────────────────────────────────


class SubtitleProvider(ABC):
    """Abstract base class for subtitle providers.

    Providers are context managers that handle initialization/cleanup.

    Class-level attributes for plugin system:
        config_fields: Declarative config field definitions for dynamic UI forms.
            Each dict: {"key": str, "label": str, "type": "text"|"password"|"number",
                        "required": bool, "default": str}
        rate_limit: (max_requests, window_seconds); (0, 0) = no limit.
        timeout: Request timeout in seconds.
        max_retries: Number of retries on transient failure.
        is_plugin: True for externally loaded plugins, False for built-in providers.
    """

    name: str = "unknown"
    languages: set[str] = set()  # Supported ISO 639-1 codes

    # Plugin system attributes (declarative, read by ProviderManager)
    config_fields: list[dict] = []
    rate_limit: tuple[int, int] = (0, 0)
    timeout: int = 30
    max_retries: int = 2
    is_plugin: bool = False

    # Budget-gate metadata (consumed by services.provider_budget.ProviderBudgetManager).
    # Subclasses SHOULD override with provider-specific limits per tier; the default
    # here is deliberately conservative so an un-updated provider still gets throttled
    # rather than hammering an external API unbounded.
    # Format: {"<tier>": {"second": int, "hour": int, "day": int}, ...}
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 60, "day": 500},
    }

    # Active tier — providers that support multiple tiers (e.g. free/vip) may
    # update this during initialize(). The ProviderBudgetManager looks up
    # rate_limits[tier]; unknown tiers fall back to "free".
    tier: str = "free"

    def __init__(self, **config):
        self.config = config
        self._initialized = False

    def __enter__(self):
        self.initialize()
        self._initialized = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()
        self._initialized = False
        return False

    def initialize(self):
        """Initialize provider (login, setup session). Override if needed.

        The base implementation is intentionally a no-op: providers that
        require authentication or session setup override this method.
        Providers with no setup requirements (e.g. anonymous scraping) inherit
        this no-op directly.
        """
        # Intentional no-op: stateless providers need no initialization.

    def terminate(self):
        """Cleanup provider (logout, close session). Override if needed.

        The base implementation is intentionally a no-op: providers that hold
        open sessions or auth tokens override this method to release resources.
        Providers with no teardown requirements inherit this no-op directly.
        """
        # Intentional no-op: stateless providers need no cleanup.

    @abstractmethod
    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Search for subtitles matching the query.

        Args:
            query: Video information and language preferences

        Returns:
            List of SubtitleResult objects (unsorted — scoring done by manager)
        """
        ...

    @abstractmethod
    def download(self, result: SubtitleResult) -> bytes:
        """Download a subtitle's content.

        Args:
            result: A SubtitleResult from search()

        Returns:
            Raw subtitle file content (bytes)
        """
        ...

    def result_for_download(self, subtitle_id: str, language: str = "") -> SubtitleResult:
        """Rebuild a downloadable result from a stored ``subtitle_id`` — without a search.

        Callers that already know exactly which subtitle they want (the repair
        runner re-fetching a file it downloaded before) skip the search and go
        straight to ``download()``. The id alone is enough for providers that
        resolve it server-side; providers that download from a URL must override
        this and rebuild that URL, or ``download()`` gets nothing to fetch.

        Raises:
            ValueError: The id is not in this provider's stored format.
        """
        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=subtitle_id,
            language=language,
            provider_data={"file_id": subtitle_id},
        )

    def health_check(self) -> tuple[bool, str]:
        """Check if the provider is reachable.

        Returns:
            (is_healthy, message)
        """
        return True, "OK"
