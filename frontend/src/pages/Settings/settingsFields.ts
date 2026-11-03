import { Server, Languages, Zap, Globe, Cog } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// ─── Navigation Groups ────────────────────────────────────────────────────────

interface NavGroup {
  title: string
  icon: LucideIcon
  items: string[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Connections',
    icon: Server,
    items: ['Sonarr', 'Radarr', 'Library Sources', 'Media Servers', 'API Keys'],
  },
  {
    title: 'Languages & Subtitles',
    icon: Languages,
    items: ['Languages', 'Scoring', 'Subtitle Tools', 'Cleanup'],
  },
  {
    title: 'Providers',
    icon: Globe,
    items: ['Providers'],
  },
  {
    title: 'Automation',
    icon: Zap,
    items: ['Automation', 'Wanted', 'Whisper', 'Translation', 'Translation Backends', 'Prompt Presets'],
  },
  {
    title: 'System',
    icon: Cog,
    items: ['General', 'Events & Hooks', 'Backup', 'Integrations', 'Notification Templates', 'Security', 'Protokoll'],
  },
]

// Flat list derived from groups (preserves ordering for legacy code)
export const TABS = NAV_GROUPS.flatMap((g) => g.items)

// ─── Field Configuration ──────────────────────────────────────────────────────

export interface FieldConfig {
  key: string
  label: string
  type: 'text' | 'number' | 'password' | 'toggle' | 'language-select' | 'select'
  placeholder?: string
  options?: { value: string; labelKey: string }[]
  tab: string
  /** i18n key (settings namespace) of the help text; resolve with t() at use time. */
  descriptionKey?: string
  advanced?: boolean
}

export const FIELDS: FieldConfig[] = [
  // General
  { key: 'port', label: 'Port', type: 'number', tab: 'General',
    descriptionKey: 'settings_fields.port' },
  { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'Leave empty to disable', tab: 'General',
    descriptionKey: 'settings_fields.api_key' },
  { key: 'log_level', label: 'Log Level', type: 'text', placeholder: 'INFO', tab: 'General',
    descriptionKey: 'settings_fields.log_level' },
  { key: 'media_path', label: 'Media Path', type: 'text', placeholder: '/media', tab: 'General',
    descriptionKey: 'settings_fields.media_path' },
  { key: 'db_path', label: 'Database Path', type: 'text', placeholder: '/config/sublarr.db', tab: 'General',
    descriptionKey: 'settings_fields.db_path',
    advanced: true },
  // Translation
  { key: 'source_language', label: 'Source Language', type: 'language-select', tab: 'Translation',
    descriptionKey: 'settings_fields.source_language' },
  { key: 'target_language', label: 'Target Language', type: 'language-select', tab: 'Translation',
    descriptionKey: 'settings_fields.target_language' },
  { key: 'source_language_name', label: 'Source Language Name (Override)', type: 'text', placeholder: 'English', tab: 'Translation',
    descriptionKey: 'settings_fields.source_language_name',
    advanced: true },
  { key: 'target_language_name', label: 'Target Language Name (Override)', type: 'text', placeholder: 'German', tab: 'Translation',
    descriptionKey: 'settings_fields.target_language_name',
    advanced: true },
  { key: 'hi_removal_enabled', label: 'Remove Hearing Impaired Tags', type: 'toggle', tab: 'Translation',
    descriptionKey: 'settings_fields.hi_removal_enabled' },
  { key: 'auto_translate_any_source', label: 'Translate From Any Source Language', type: 'toggle', tab: 'Translation',
    descriptionKey: 'settings_fields.auto_translate_any_source' },
  { key: 'auto_translate_provider_multilang', label: 'Provider Multi-Language Source Search', type: 'toggle', tab: 'Translation',
    descriptionKey: 'settings_fields.auto_translate_provider_multilang' },
  { key: 'hi_preference', label: 'Hearing Impaired Preference', type: 'select', tab: 'Translation',
    descriptionKey: 'settings_fields.hi_preference',
    options: [
      { value: 'include', labelKey: 'settings_fields.hi_preference_options.include' },
      { value: 'prefer', labelKey: 'settings_fields.hi_preference_options.prefer' },
      { value: 'exclude', labelKey: 'settings_fields.hi_preference_options.exclude' },
      { value: 'only', labelKey: 'settings_fields.hi_preference_options.only' },
    ] },
  // Automation — Provider Re-ranking
  { key: 'provider_reranking_enabled', label: 'Auto Re-ranking', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.provider_reranking_enabled' },
  { key: 'provider_reranking_min_downloads', label: 'Min Downloads (for re-ranking)', type: 'number', placeholder: '20', tab: 'Automation',
    descriptionKey: 'settings_fields.provider_reranking_min_downloads',
    advanced: true },
  { key: 'provider_reranking_max_modifier', label: 'Max Modifier (±pts)', type: 'number', placeholder: '50', tab: 'Automation',
    descriptionKey: 'settings_fields.provider_reranking_max_modifier',
    advanced: true },
  // Automation — Upgrade
  { key: 'upgrade_enabled', label: 'Upgrade Enabled', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.upgrade_enabled' },
  { key: 'upgrade_prefer_ass', label: 'Prefer ASS over SRT', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.upgrade_prefer_ass' },
  { key: 'upgrade_min_score_delta', label: 'Min Score Delta', type: 'number', placeholder: '50', tab: 'Automation',
    descriptionKey: 'settings_fields.upgrade_min_score_delta',
    advanced: true },
  { key: 'upgrade_window_days', label: 'Upgrade Window (days)', type: 'number', placeholder: '7', tab: 'Automation',
    descriptionKey: 'settings_fields.upgrade_window_days',
    advanced: true },
  { key: 'upgrade_scan_interval_hours', label: 'Upgrade Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '0', tab: 'Automation',
    descriptionKey: 'settings_fields.upgrade_scan_interval_hours' },
  // Automation — Webhook
  { key: 'webhook_delay_minutes', label: 'Webhook Delay (minutes)', type: 'number', placeholder: '5', tab: 'Automation',
    descriptionKey: 'settings_fields.webhook_delay_minutes',
    advanced: true },
  { key: 'webhook_auto_scan', label: 'Auto-Scan after Download', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.webhook_auto_scan' },
  { key: 'webhook_auto_search', label: 'Auto-Search Providers', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.webhook_auto_search' },
  { key: 'webhook_auto_translate', label: 'Auto-Translate Found Subs', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.webhook_auto_translate' },
  // Automation — Remux / Stream Removal
  { key: 'remux_trash_dir', label: 'Remux Trash Folder', type: 'text', placeholder: '.sublarr', tab: 'Automation',
    descriptionKey: 'settings_fields.remux_trash_dir' },
  { key: 'remux_backup_retention_days', label: 'Remux Backup Retention (days, 0=forever)', type: 'number', placeholder: '7', tab: 'Automation',
    descriptionKey: 'settings_fields.remux_backup_retention_days' },
  { key: 'remux_use_reflink', label: 'Use CoW Reflink for Backups', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.remux_use_reflink',
    advanced: true },
  { key: 'remux_arr_pause_enabled', label: 'Pause *arr during Remux', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.remux_arr_pause_enabled',
    advanced: true },
  { key: 'remux_hardlink_policy', label: 'Hardlink Policy', type: 'select', tab: 'Automation',
    options: [
      { value: 'skip', labelKey: 'settings_fields.remux_hardlink_policy_options.skip' },
      { value: 'warn', labelKey: 'settings_fields.remux_hardlink_policy_options.warn' },
      { value: 'allow', labelKey: 'settings_fields.remux_hardlink_policy_options.allow' },
    ],
    descriptionKey: 'settings_fields.remux_hardlink_policy' },
  // Automation — Search Scheduler
  { key: 'wanted_search_interval_hours', label: 'Search Interval (hours, 0=disabled)', type: 'number', placeholder: '24', tab: 'Automation',
    descriptionKey: 'settings_fields.wanted_search_interval_hours',
    advanced: true },
  { key: 'wanted_search_on_startup', label: 'Search on Startup', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.wanted_search_on_startup' },
  { key: 'wanted_search_max_items_per_run', label: 'Max Items per Search Run', type: 'number', placeholder: '50', tab: 'Automation',
    descriptionKey: 'settings_fields.wanted_search_max_items_per_run',
    advanced: true },
  { key: 'wanted_search_order', label: 'Search Order (fair/newest_first/weighted)', type: 'text', placeholder: 'fair', tab: 'Automation',
    descriptionKey: 'settings_fields.wanted_search_order',
    advanced: true },
  // Wanted
  { key: 'wanted_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_scan_interval_hours',
    advanced: true },
  { key: 'wanted_anime_only', label: 'Anime Only (Sonarr)', type: 'toggle', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_anime_only' },
  { key: 'wanted_anime_movies_only', label: 'Anime Movies Only (Radarr)', type: 'toggle', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_anime_movies_only' },
  { key: 'wanted_scan_on_startup', label: 'Scan on Startup', type: 'toggle', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_scan_on_startup' },
  { key: 'wanted_auto_extract', label: 'Auto-extract embedded subs on scan', type: 'toggle', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_auto_extract' },
  { key: 'wanted_auto_translate', label: 'Auto-translate after extraction', type: 'toggle', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_auto_translate' },
  { key: 'wanted_max_search_attempts', label: 'Max Search Attempts', type: 'number', placeholder: '3', tab: 'Wanted',
    descriptionKey: 'settings_fields.wanted_max_search_attempts',
    advanced: true },
  // Sonarr
  { key: 'sonarr_url', label: 'Sonarr URL', type: 'text', placeholder: 'http://localhost:8989', tab: 'Sonarr',
    descriptionKey: 'settings_fields.sonarr_url' },
  { key: 'sonarr_api_key', label: 'Sonarr API Key', type: 'password', tab: 'Sonarr',
    descriptionKey: 'settings_fields.sonarr_api_key' },
  // Radarr
  { key: 'radarr_url', label: 'Radarr URL', type: 'text', placeholder: 'http://localhost:7878', tab: 'Radarr',
    descriptionKey: 'settings_fields.radarr_url' },
  { key: 'radarr_api_key', label: 'Radarr API Key', type: 'password', tab: 'Radarr',
    descriptionKey: 'settings_fields.radarr_api_key' },
  // Library Sources (Standalone Mode)
  { key: 'standalone_enabled', label: 'Enable Standalone Mode', type: 'toggle', tab: 'Library Sources',
    descriptionKey: 'settings_fields.standalone_enabled' },
  { key: 'tmdb_api_key', label: 'TMDB API Key (Bearer Token)', type: 'password', tab: 'Library Sources',
    descriptionKey: 'settings_fields.tmdb_api_key' },
  { key: 'tvdb_api_key', label: 'TVDB API Key (Optional)', type: 'password', tab: 'Library Sources',
    descriptionKey: 'settings_fields.tvdb_api_key' },
  { key: 'tvdb_pin', label: 'TVDB PIN (Optional)', type: 'password', tab: 'Library Sources',
    descriptionKey: 'settings_fields.tvdb_pin' },
  { key: 'standalone_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Library Sources',
    descriptionKey: 'settings_fields.standalone_scan_interval_hours',
    advanced: true },
  { key: 'standalone_debounce_seconds', label: 'File Detection Debounce (seconds)', type: 'number', placeholder: '10', tab: 'Library Sources',
    descriptionKey: 'settings_fields.standalone_debounce_seconds',
    advanced: true },
  { key: 'standalone_skip_extras', label: 'Skip Extra Files (Trailer, Featurettes …)', type: 'toggle', tab: 'Library Sources',
    descriptionKey: 'settings_fields.standalone_skip_extras',
    advanced: true },
  // Automation — Sidecar Cleanup
  { key: 'auto_cleanup_after_extract', label: 'Nach Extraktion bereinigen', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.auto_cleanup_after_extract' },
  { key: 'auto_cleanup_keep_languages', label: 'Behalte Sprachen (Codes)', type: 'text', placeholder: 'de,en', tab: 'Automation',
    descriptionKey: 'settings_fields.auto_cleanup_keep_languages' },
  { key: 'auto_cleanup_keep_formats', label: 'Bevorzugtes Format', type: 'text', placeholder: 'any', tab: 'Automation',
    descriptionKey: 'settings_fields.auto_cleanup_keep_formats',
    advanced: true },
  // Automation — Subtitle Trash
  { key: 'subtitle_trash_retention_days', label: 'Trash Retention (days)', type: 'number', placeholder: '30', tab: 'Automation',
    descriptionKey: 'settings_fields.subtitle_trash_retention_days' },
  // Automation — NFO Export (expert)
  { key: 'auto_nfo_export', label: 'Auto NFO Export', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.auto_nfo_export',
    advanced: true },
  // Automation — Web Player
  { key: 'streaming_enabled', label: 'Enable Video Streaming', type: 'toggle', tab: 'Automation',
    descriptionKey: 'settings_fields.streaming_enabled',
    advanced: true },
]

// ─── Tab i18n Keys ────────────────────────────────────────────────────────────

export const TAB_KEYS: Record<string, string> = {
  'General': 'tabs.general',
  'API Keys': 'tabs.api_keys',
  'Translation': 'tabs.translation',
  'Translation Backends': 'tabs.translation_backends',
  'Languages': 'tabs.languages',
  'Automation': 'tabs.automation',
  'Wanted': 'tabs.wanted',
  'Providers': 'tabs.providers',
  'Sonarr': 'tabs.sonarr',
  'Radarr': 'tabs.radarr',
  'Library Sources': 'tabs.library_sources',
  'Media Servers': 'tabs.media_servers',
  'Whisper': 'tabs.whisper',
  'Events & Hooks': 'tabs.events_hooks',
  'Scoring': 'tabs.scoring',
  'Backup': 'tabs.backup',
  'Subtitle Tools': 'tabs.subtitle_tools',
  'Cleanup': 'tabs.cleanup',
  'Integrations': 'tabs.integrations',
  'Notification Templates': 'tabs.notification_templates',
  'Prompt Presets': 'tabs.prompt_presets',
  'Protokoll': 'protokoll_tab',
}
