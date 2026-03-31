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
    AnidbAbsoluteMapping,
    BlacklistEntry,
    ChapterCache,
    ConfigEntry,
    DailyStats,
    FansubPreference,
    FfprobeCache,
    FilterPreset,
    Job,
    LanguageProfile,
    MovieLanguageProfile,
    SeriesLanguageProfile,
    SeriesSettings,
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
from db.models.plugins import (
    InstalledPlugin,
    MarketplaceCache,
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
    TranslationMemory,
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
    "SeriesSettings",
    "FansubPreference",
    "AnidbAbsoluteMapping",
    "ChapterCache",
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
    "TranslationMemory",
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
    # plugins / marketplace
    "MarketplaceCache",
    "InstalledPlugin",
]
