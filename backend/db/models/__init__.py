"""SQLAlchemy ORM models for Sublarr database.

All models use Flask-SQLAlchemy's db.Model as the base class.
Import all models from here to ensure Alembic autogenerate detects them.
"""

from db.models.core import (
    Job,
    DailyStats,
    ConfigEntry,
    WantedItem,
    UpgradeHistory,
    LanguageProfile,
    SeriesLanguageProfile,
    MovieLanguageProfile,
    FfprobeCache,
    BlacklistEntry,
)
from db.models.providers import (
    ProviderCache,
    SubtitleDownload,
    ProviderStats,
    ProviderScoreModifier,
    ScoringWeights,
)
from db.models.translation import (
    TranslationConfigHistory,
    GlossaryEntry,
    PromptPreset,
    TranslationBackendStats,
    WhisperJob,
)
from db.models.hooks import (
    HookConfig,
    WebhookConfig,
    HookLog,
)
from db.models.standalone import (
    WatchedFolder,
    StandaloneSeries,
    StandaloneMovie,
    MetadataCache,
    AnidbMapping,
)
from db.models.quality import SubtitleHealthResult

__all__ = [
    # core
    "Job",
    "DailyStats",
    "ConfigEntry",
    "WantedItem",
    "UpgradeHistory",
    "LanguageProfile",
    "SeriesLanguageProfile",
    "MovieLanguageProfile",
    "FfprobeCache",
    "BlacklistEntry",
    # providers
    "ProviderCache",
    "SubtitleDownload",
    "ProviderStats",
    "ProviderScoreModifier",
    "ScoringWeights",
    # translation
    "TranslationConfigHistory",
    "GlossaryEntry",
    "PromptPreset",
    "TranslationBackendStats",
    "WhisperJob",
    # hooks
    "HookConfig",
    "WebhookConfig",
    "HookLog",
    # standalone
    "WatchedFolder",
    "StandaloneSeries",
    "StandaloneMovie",
    "MetadataCache",
    "AnidbMapping",
    # quality
    "SubtitleHealthResult",
]
