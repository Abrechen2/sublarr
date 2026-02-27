"""Event catalog — discoverable registry of all Sublarr internal events.

Defines blinker signals in a Namespace and an EVENT_CATALOG dict mapping
event names to metadata (label, description, payload keys). This is the
single source of truth for what events exist in the system.

Payload keys intentionally omit secrets and absolute filesystem paths.
"""

from blinker import Namespace

# All Sublarr signals live in this namespace
sublarr_signals = Namespace()

# Catalog version for future payload schema evolution
CATALOG_VERSION = 1

# ---- Signal definitions --------------------------------------------------------

subtitle_downloaded = sublarr_signals.signal("subtitle_downloaded")
translation_complete = sublarr_signals.signal("translation_complete")
translation_failed = sublarr_signals.signal("translation_failed")
provider_search_complete = sublarr_signals.signal("provider_search_complete")
provider_failed = sublarr_signals.signal("provider_failed")
wanted_scan_complete = sublarr_signals.signal("wanted_scan_complete")
wanted_item_processed = sublarr_signals.signal("wanted_item_processed")
upgrade_complete = sublarr_signals.signal("upgrade_complete")
batch_complete = sublarr_signals.signal("batch_complete")
webhook_received = sublarr_signals.signal("webhook_received")
config_updated = sublarr_signals.signal("config_updated")
whisper_complete = sublarr_signals.signal("whisper_complete")
whisper_failed = sublarr_signals.signal("whisper_failed")
hook_executed = sublarr_signals.signal("hook_executed")
standalone_scan_complete = sublarr_signals.signal("standalone_scan_complete")
standalone_file_detected = sublarr_signals.signal("standalone_file_detected")

# ---- Catalog dict (machine-readable metadata) ----------------------------------

EVENT_CATALOG: dict[str, dict] = {
    "subtitle_downloaded": {
        "signal": subtitle_downloaded,
        "label": "Subtitle Downloaded",
        "description": "A subtitle file was successfully downloaded from a provider.",
        "payload_keys": [
            "provider_name",
            "language",
            "format",
            "score",
            "series_title",
            "season",
            "episode",
            "movie_title",
        ],
    },
    "translation_complete": {
        "signal": translation_complete,
        "label": "Translation Complete",
        "description": "A subtitle translation job finished successfully.",
        "payload_keys": [
            "job_id",
            "source_language",
            "target_language",
            "backend_name",
            "duration_ms",
            "series_title",
            "movie_title",
        ],
    },
    "translation_failed": {
        "signal": translation_failed,
        "label": "Translation Failed",
        "description": "A subtitle translation job failed.",
        "payload_keys": [
            "job_id",
            "source_language",
            "target_language",
            "backend_name",
            "error",
            "series_title",
            "movie_title",
        ],
    },
    "provider_search_complete": {
        "signal": provider_search_complete,
        "label": "Provider Search Complete",
        "description": "A provider search returned results.",
        "payload_keys": [
            "provider_name",
            "result_count",
            "best_score",
            "series_title",
            "season",
            "episode",
            "movie_title",
        ],
    },
    "provider_failed": {
        "signal": provider_failed,
        "label": "Provider Failed",
        "description": "A provider search or download failed.",
        "payload_keys": [
            "provider_name",
            "error",
            "error_type",
            "series_title",
            "movie_title",
        ],
    },
    "wanted_scan_complete": {
        "signal": wanted_scan_complete,
        "label": "Wanted Scan Complete",
        "description": "The periodic wanted scanner completed a full scan cycle.",
        "payload_keys": [
            "total_items",
            "new_items",
            "removed_items",
            "duration_ms",
        ],
    },
    "wanted_item_processed": {
        "signal": wanted_item_processed,
        "label": "Wanted Item Processed",
        "description": "A single wanted item was searched and processed.",
        "payload_keys": [
            "item_id",
            "title",
            "season_episode",
            "status",
            "provider_name",
            "score",
        ],
    },
    "upgrade_complete": {
        "signal": upgrade_complete,
        "label": "Upgrade Complete",
        "description": "A subtitle was upgraded (e.g. SRT replaced with ASS).",
        "payload_keys": [
            "title",
            "old_format",
            "new_format",
            "old_score",
            "new_score",
            "provider_name",
        ],
    },
    "batch_complete": {
        "signal": batch_complete,
        "label": "Batch Complete",
        "description": "A batch translation or search operation completed.",
        "payload_keys": [
            "total",
            "succeeded",
            "failed",
            "skipped",
            "duration_ms",
        ],
    },
    "webhook_received": {
        "signal": webhook_received,
        "label": "Webhook Received",
        "description": "An incoming webhook from Sonarr or Radarr was received.",
        "payload_keys": [
            "source",
            "event_type",
            "title",
            "season",
            "episode",
        ],
    },
    "config_updated": {
        "signal": config_updated,
        "label": "Config Updated",
        "description": "Application configuration was changed.",
        "payload_keys": [
            "changed_keys",
            "source",
        ],
    },
    "whisper_complete": {
        "signal": whisper_complete,
        "label": "Whisper Complete",
        "description": "A Whisper speech-to-text job finished successfully.",
        "payload_keys": [
            "job_id",
            "backend_name",
            "detected_language",
            "segment_count",
            "duration_seconds",
            "processing_time_ms",
        ],
    },
    "whisper_failed": {
        "signal": whisper_failed,
        "label": "Whisper Failed",
        "description": "A Whisper speech-to-text job failed.",
        "payload_keys": [
            "job_id",
            "backend_name",
            "error",
        ],
    },
    "hook_executed": {
        "signal": hook_executed,
        "label": "Hook Executed",
        "description": "A hook or webhook was executed (meta-event for monitoring).",
        "payload_keys": [
            "hook_id",
            "webhook_id",
            "hook_type",
            "event_name",
            "success",
            "duration_ms",
        ],
    },
    "standalone_scan_complete": {
        "signal": standalone_scan_complete,
        "label": "Standalone Scan Complete",
        "description": "A standalone folder scan completed.",
        "payload_keys": [
            "folders_scanned",
            "files_found",
            "wanted_added",
            "duration_seconds",
        ],
    },
    "standalone_file_detected": {
        "signal": standalone_file_detected,
        "label": "Standalone File Detected",
        "description": "A new media file was detected in a watched folder.",
        "payload_keys": [
            "path",
            "type",
            "wanted",
        ],
    },
}
