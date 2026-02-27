"""SQLAlchemy ORM models for Sublarr database.

All models use Flask-SQLAlchemy's db.Model as the base class.
Import all models from here to ensure Alembic autogenerate detects them.
"""

from db.models.cleanup import (
    CleanupHistory,
    CleanupRule,
    SubtitleHash,
)
from db.models.core import (
    BlacklistEntry,
    ConfigEntry,
    DailyStats,
    FfprobeCache,
    FilterPreset,
    Job,
    LanguageProfile,
    MovieLanguageProfile,
    SeriesLanguageProfile,
    UpgradeHistory,
    WantedItem,
)
from db.models.hooks import (
    HookConfig,
    HookLog,
    WebhookConfig,
)
from db.models.notifications import (
    NotificationHistory,
    NotificationTemplate,
    QuietHoursConfig,
)
from db.models.providers import (
    ProviderCache,
    ProviderScoreModifier,
    ProviderStats,
    ScoringWeights,
    SubtitleDownload,
)
from db.models.quality import SubtitleHealthResult
from db.models.standalone import (
    AnidbMapping,
    MetadataCache,
    StandaloneMovie,
    StandaloneSeries,
    WatchedFolder,
)
from db.models.translation import (
    GlossaryEntry,
    PromptPreset,
    TranslationBackendStats,
    TranslationConfigHistory,
    WhisperJob,
)

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
    # filter presets
    "FilterPreset",
    # cleanup
    "SubtitleHash",
    "CleanupRule",
    "CleanupHistory",
    # notifications
    "NotificationTemplate",
    "NotificationHistory",
    "QuietHoursConfig",
]
