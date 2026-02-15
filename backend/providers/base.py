"""Abstract base class for subtitle providers and shared data models.

All providers implement the same interface: search for subtitles matching
a video query and download the best result. Adapted from Bazarr/subliminal
patterns but simplified for Sublarr's focused use case.

License: GPL-3.0 (compatible with Bazarr source)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProviderError(Exception):
    """Base exception for provider errors (auth, rate-limit, network)."""
    pass


class ProviderAuthError(ProviderError):
    """Authentication or authorization failed."""
    pass


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""
    pass


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""
    pass


class SubtitleFormat(str, Enum):
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
    year: Optional[int] = None
    imdb_id: str = ""  # e.g. "tt1234567"
    tmdb_id: Optional[int] = None  # The Movie Database ID
    genres: list[str] = field(default_factory=list)  # Movie genres

    # Episode-specific
    series_title: str = ""
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_title: str = ""

    # Anime IDs (for specialized providers)
    anidb_id: Optional[int] = None
    anidb_episode_id: Optional[int] = None
    anilist_id: Optional[int] = None
    tvdb_id: Optional[int] = None

    # Release info (for scoring)
    release_group: str = ""
    source: str = ""  # BluRay, WEB-DL, etc.
    resolution: str = ""  # 1080p, 720p
    video_codec: str = ""  # x264, x265

    # Language preferences
    languages: list[str] = field(default_factory=list)  # ISO 639-1 codes to search for

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
    content: Optional[bytes] = field(default=None, repr=False)

    # Matching metadata
    release_info: str = ""
    hearing_impaired: bool = False
    forced: bool = False
    fps: Optional[float] = None

    # Scoring
    score: int = 0
    matches: set[str] = field(default_factory=set)

    # Provider metadata
    provider_data: dict = field(default_factory=dict)

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
    "hearing_impaired": 1,
    "format_bonus": 50,
}


def compute_score(result: SubtitleResult, query: VideoQuery) -> int:
    """Compute match score for a subtitle result against a video query."""
    weights = EPISODE_SCORES if query.is_episode else MOVIE_SCORES
    score = 0

    for match in result.matches:
        score += weights.get(match, 0)

    # ASS format bonus (Sublarr always prefers ASS)
    if result.is_ass:
        score += weights.get("format_bonus", 0)

    result.score = score
    return score


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
        """Initialize provider (login, setup session). Override if needed."""
        pass

    def terminate(self):
        """Cleanup provider (logout, close session). Override if needed."""
        pass

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

    def health_check(self) -> tuple[bool, str]:
        """Check if the provider is reachable.

        Returns:
            (is_healthy, message)
        """
        return True, "OK"
