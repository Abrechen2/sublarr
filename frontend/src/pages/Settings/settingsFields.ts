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
  options?: { value: string; label: string }[]
  tab: string
  description?: string
  advanced?: boolean
}

export const FIELDS: FieldConfig[] = [
  // General
  { key: 'port', label: 'Port', type: 'number', tab: 'General',
    description: 'HTTP-Port auf dem Sublarr lauscht. Standard: 5765.' },
  { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'Leave empty to disable', tab: 'General',
    description: 'Optionaler API-Key für den X-Api-Key Header. Leer lassen um Auth zu deaktivieren.' },
  { key: 'log_level', label: 'Log Level', type: 'text', placeholder: 'INFO', tab: 'General',
    description: 'Logging-Stufe: DEBUG, INFO, WARNING, ERROR.' },
  { key: 'media_path', label: 'Media Path', type: 'text', placeholder: '/media', tab: 'General',
    description: 'Wurzelpfad des Medienverzeichnisses. Alle Medienpfade müssen darunter liegen.' },
  { key: 'db_path', label: 'Database Path', type: 'text', placeholder: '/config/sublarr.db', tab: 'General',
    description: 'SQLite-Datenbankdatei. Nur ändern wenn die DB verschoben wurde.',
    advanced: true },
  // Translation
  { key: 'source_language', label: 'Source Language', type: 'language-select', tab: 'Translation',
    description: 'Quellsprache der Untertitel (z.B. Englisch). Setzt auch den Sprachnamen für LLM-Prompts.' },
  { key: 'target_language', label: 'Target Language', type: 'language-select', tab: 'Translation',
    description: 'Zielsprache für Übersetzungen und Provider-Suche (z.B. Deutsch).' },
  { key: 'source_language_name', label: 'Source Language Name (Override)', type: 'text', placeholder: 'English', tab: 'Translation',
    description: 'Vollständiger Name der Quellsprache für LLM-Prompts. Wird automatisch beim Sprachwechsel gesetzt.',
    advanced: true },
  { key: 'target_language_name', label: 'Target Language Name (Override)', type: 'text', placeholder: 'German', tab: 'Translation',
    description: 'Vollständiger Name der Zielsprache für LLM-Prompts. Wird automatisch beim Sprachwechsel gesetzt.',
    advanced: true },
  { key: 'hi_removal_enabled', label: 'Remove Hearing Impaired Tags', type: 'toggle', tab: 'Translation',
    description: 'Entfernt [Geräuschbeschreibungen] und (Sprechertags) aus Untertiteln.' },
  { key: 'auto_translate_any_source', label: 'Translate From Any Source Language', type: 'toggle', tab: 'Translation',
    description: 'Übersetzt die fehlende Zielsprache aus JEDER vorhandenen Quell-Sprache (bevorzugt die Profil-/Standard-Quelle). Aus: es wird nur die bevorzugte Quellsprache genutzt.' },
  { key: 'auto_translate_provider_multilang', label: 'Provider Multi-Language Source Search', type: 'toggle', tab: 'Translation',
    description: 'Sucht bei Providern nach Quell-Untertiteln in mehreren Sprachen (mehr Treffer, mehr API-Verbrauch). Nur wirksam, wenn „aus beliebiger Quelle" aktiv ist.' },
  { key: 'hi_preference', label: 'Hearing Impaired Preference', type: 'select', tab: 'Translation',
    description: 'Wie Untertitel mit HI-Tags bei der Provider-Suche behandelt werden.',
    options: [
      { value: 'include', label: 'Include (no preference)' },
      { value: 'prefer', label: 'Prefer HI (+30 score)' },
      { value: 'exclude', label: 'Exclude HI (−999 penalty)' },
      { value: 'only', label: 'Only HI (non-HI excluded)' },
    ] },
  { key: 'forced_preference', label: 'Forced Subtitle Preference', type: 'select', tab: 'Translation',
    description: 'Wie Forced-Untertitel (für Fremdsprachen-Szenen) bei der Provider-Suche behandelt werden.',
    options: [
      { value: 'include', label: 'Include (no preference)' },
      { value: 'prefer', label: 'Prefer forced (+30 score)' },
      { value: 'exclude', label: 'Exclude forced (−999 penalty)' },
      { value: 'only', label: 'Only forced (non-forced excluded)' },
    ] },
  // Automation — Provider Re-ranking
  { key: 'provider_reranking_enabled', label: 'Auto Re-ranking', type: 'toggle', tab: 'Automation',
    description: 'Provider-Score-Modifier automatisch aus Download-History berechnen. Gute Provider bekommen Bonus, schlechte Penalty.' },
  { key: 'provider_reranking_min_downloads', label: 'Min Downloads (for re-ranking)', type: 'number', placeholder: '20', tab: 'Automation',
    description: 'Mindest-Anzahl erfolgreicher Downloads bevor ein Modifier berechnet wird.',
    advanced: true },
  { key: 'provider_reranking_max_modifier', label: 'Max Modifier (±pts)', type: 'number', placeholder: '50', tab: 'Automation',
    description: 'Maximaler absoluter Score-Modifier der durch Re-ranking vergeben wird.',
    advanced: true },
  // Automation — Upgrade
  { key: 'upgrade_enabled', label: 'Upgrade Enabled', type: 'toggle', tab: 'Automation',
    description: 'Automatisch bessere Untertitel suchen wenn Score-Schwellenwert nicht erreicht.' },
  { key: 'upgrade_prefer_ass', label: 'Prefer ASS over SRT', type: 'toggle', tab: 'Automation',
    description: 'ASS-Format (mit Styling) gegenüber SRT bevorzugen.' },
  { key: 'upgrade_min_score_delta', label: 'Min Score Delta', type: 'number', placeholder: '50', tab: 'Automation',
    description: 'Mindest-Score-Unterschied um einen Upgrade-Download zu rechtfertigen.',
    advanced: true },
  { key: 'upgrade_window_days', label: 'Upgrade Window (days)', type: 'number', placeholder: '7', tab: 'Automation',
    description: 'Upgrade-Versuche nur innerhalb dieses Zeitfensters nach dem Release.',
    advanced: true },
  { key: 'upgrade_scan_interval_hours', label: 'Upgrade Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '0', tab: 'Automation',
    description: 'Wie oft der Upgrade-Scanner nach Kandidaten sucht. 0 = deaktiviert.' },
  // Automation — Webhook
  { key: 'webhook_delay_minutes', label: 'Webhook Delay (minutes)', type: 'number', placeholder: '5', tab: 'Automation',
    description: 'Wartezeit nach Sonarr/Radarr-Webhook bevor die Suche startet.',
    advanced: true },
  { key: 'webhook_auto_scan', label: 'Auto-Scan after Download', type: 'toggle', tab: 'Automation',
    description: 'Nach Sonarr/Radarr-Download automatisch auf eingebettete Subs scannen.' },
  { key: 'webhook_auto_search', label: 'Auto-Search Providers', type: 'toggle', tab: 'Automation',
    description: 'Nach Download automatisch bei Subtitle-Providern suchen.' },
  { key: 'webhook_auto_translate', label: 'Auto-Translate Found Subs', type: 'toggle', tab: 'Automation',
    description: 'Gefundene Untertitel automatisch übersetzen.' },
  // Automation — Remux / Stream Removal
  { key: 'remux_trash_dir', label: 'Remux Trash Folder', type: 'text', placeholder: '.sublarr', tab: 'Automation',
    description: 'Ordner für Backups gelöschter Streams. Relativ zum Medienpfad (z.B. .sublarr) oder absoluter Pfad. Backups landen in <trash>/<datum>/<datei>.<ts>.bak.' },
  { key: 'remux_backup_retention_days', label: 'Remux Backup Retention (days, 0=forever)', type: 'number', placeholder: '7', tab: 'Automation',
    description: 'Nach wie vielen Tagen werden Remux-Backups endgültig gelöscht. 0 = nie.' },
  { key: 'remux_use_reflink', label: 'Use CoW Reflink for Backups', type: 'toggle', tab: 'Automation',
    description: 'Auf Btrfs/XFS wird cp --reflink=auto für kostenlose Backups genutzt.',
    advanced: true },
  { key: 'remux_arr_pause_enabled', label: 'Pause *arr during Remux', type: 'toggle', tab: 'Automation',
    description: 'Sonarr/Radarr-Ordner-Monitoring während des Remux pausieren.',
    advanced: true },
  { key: 'remux_hardlink_policy', label: 'Hardlink Policy', type: 'select', tab: 'Automation',
    options: [
      { value: 'skip', label: 'Skip (hardlinked Dateien nie remuxen)' },
      { value: 'warn', label: 'Warn (remuxen, aber Warnung loggen)' },
      { value: 'allow', label: 'Allow (immer remuxen)' },
    ],
    description: 'Jeder Remux bricht Hardlinks (Standard bei *arr-Setups mit Torrent-Seeding): Speicherverbrauch verdoppelt sich und die Seeding-Kopie weicht ab. "Skip" (Standard) überspringt Container-Remuxe für Dateien mit mehreren Links.' },
  // Automation — Search Scheduler
  { key: 'wanted_search_interval_hours', label: 'Search Interval (hours, 0=disabled)', type: 'number', placeholder: '24', tab: 'Automation',
    description: 'Interval für automatische Provider-Suche. 0 = deaktiviert.',
    advanced: true },
  { key: 'wanted_search_on_startup', label: 'Search on Startup', type: 'toggle', tab: 'Automation',
    description: 'Provider-Suche beim Backend-Start ausführen.' },
  { key: 'wanted_search_max_items_per_run', label: 'Max Items per Search Run', type: 'number', placeholder: '50', tab: 'Automation',
    description: 'Maximale Anzahl Einträge pro automatischem Suchlauf.',
    advanced: true },
  { key: 'wanted_search_order', label: 'Search Order (fair/newest_first/weighted)', type: 'text', placeholder: 'fair', tab: 'Automation',
    description: 'Reihenfolge in der der Auto-Scheduler die Warteschlange abarbeitet.',
    advanced: true },
  // Wanted
  { key: 'wanted_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Wanted',
    description: 'Wie oft die Medienbibliothek auf fehlende Untertitel geprüft wird.',
    advanced: true },
  { key: 'wanted_anime_only', label: 'Anime Only (Sonarr)', type: 'toggle', tab: 'Wanted',
    description: 'Nur Sonarr-Serien mit Anime-Tag in die Wanted-Liste aufnehmen.' },
  { key: 'wanted_anime_movies_only', label: 'Anime Movies Only (Radarr)', type: 'toggle', tab: 'Wanted',
    description: 'Nur Radarr-Filme mit Anime-Tag in die Wanted-Liste aufnehmen.' },
  { key: 'wanted_scan_on_startup', label: 'Scan on Startup', type: 'toggle', tab: 'Wanted',
    description: 'Wanted-Scan beim Backend-Start ausführen.' },
  { key: 'wanted_auto_extract', label: 'Auto-extract embedded subs on scan', type: 'toggle', tab: 'Wanted',
    description: 'Eingebettete Untertitel aus MKV-Dateien automatisch extrahieren.' },
  { key: 'wanted_auto_translate', label: 'Auto-translate after extraction', type: 'toggle', tab: 'Wanted',
    description: 'Extrahierte Untertitel automatisch übersetzen. Erfordert Auto-Extract.' },
  { key: 'wanted_max_search_attempts', label: 'Max Search Attempts', type: 'number', placeholder: '3', tab: 'Wanted',
    description: 'Nach dieser Anzahl fehlgeschlagener Versuche wird ein Eintrag aufgegeben.',
    advanced: true },
  // Sonarr
  { key: 'sonarr_url', label: 'Sonarr URL', type: 'text', placeholder: 'http://localhost:8989', tab: 'Sonarr',
    description: 'URL der Sonarr-Instanz inkl. Port. Keine abschließenden Slashes.' },
  { key: 'sonarr_api_key', label: 'Sonarr API Key', type: 'password', tab: 'Sonarr',
    description: 'In Sonarr unter Settings → General → Security.' },
  // Radarr
  { key: 'radarr_url', label: 'Radarr URL', type: 'text', placeholder: 'http://localhost:7878', tab: 'Radarr',
    description: 'URL der Radarr-Instanz inkl. Port. Keine abschließenden Slashes.' },
  { key: 'radarr_api_key', label: 'Radarr API Key', type: 'password', tab: 'Radarr',
    description: 'In Radarr unter Settings → General → Security.' },
  // Library Sources (Standalone Mode)
  { key: 'standalone_enabled', label: 'Enable Standalone Mode', type: 'toggle', tab: 'Library Sources',
    description: 'Direktes Dateisystem-Scanning ohne Sonarr/Radarr. Media Path muss konfiguriert sein.' },
  { key: 'tmdb_api_key', label: 'TMDB API Key (Bearer Token)', type: 'password', tab: 'Library Sources',
    description: 'Bearer Token von themoviedb.org für Metadaten-Abfragen.' },
  { key: 'tvdb_api_key', label: 'TVDB API Key (Optional)', type: 'password', tab: 'Library Sources',
    description: 'API Key von thetvdb.com. Optional — TMDB reicht für die meisten Fälle.' },
  { key: 'tvdb_pin', label: 'TVDB PIN (Optional)', type: 'password', tab: 'Library Sources',
    description: 'TVDB Subscriber PIN (nur für Subscriber-Plan benötigt).' },
  { key: 'standalone_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Library Sources',
    description: 'Intervall für automatischen Dateisystem-Scan. 0 = deaktiviert.',
    advanced: true },
  { key: 'standalone_debounce_seconds', label: 'File Detection Debounce (seconds)', type: 'number', placeholder: '10', tab: 'Library Sources',
    description: 'Wartezeit nach letzter Dateiänderung bevor Scan ausgelöst wird.',
    advanced: true },
  { key: 'standalone_skip_extras', label: 'Skip Extra Files (Trailer, Featurettes …)', type: 'toggle', tab: 'Library Sources',
    description: 'Trailer, Featurettes, Samples und ähnliche Dateien beim Scan ignorieren.',
    advanced: true },
  // Automation — Sidecar Cleanup
  { key: 'auto_cleanup_after_extract', label: 'Nach Extraktion bereinigen', type: 'toggle', tab: 'Automation',
    description: 'Nach batch-extract automatisch nicht-benötigte Sprachen löschen. Benötigt keep_languages.' },
  { key: 'auto_cleanup_keep_languages', label: 'Behalte Sprachen (Codes)', type: 'text', placeholder: 'de,en', tab: 'Automation',
    description: 'Komma-getrennte ISO-639-1 Codes — Sidecars anderer Sprachen werden gelöscht. Leer = nichts löschen.' },
  { key: 'auto_cleanup_keep_formats', label: 'Bevorzugtes Format', type: 'text', placeholder: 'any', tab: 'Automation',
    description: '"ass": SRT löschen wenn ASS für dieselbe Sprache vorhanden. "srt" oder "any": beide behalten.',
    advanced: true },
  // Automation — Subtitle Trash
  { key: 'subtitle_trash_retention_days', label: 'Papierkorb-Aufbewahrung (Tage)', type: 'number', placeholder: '30', tab: 'Automation',
    description: 'Gelöschte Sidecar-Dateien werden N Tage im Papierkorb behalten und können wiederhergestellt werden. 0 = dauerhaft behalten.' },
  // Automation — NFO Export (expert)
  { key: 'auto_nfo_export', label: 'Auto NFO Export', type: 'toggle', tab: 'Automation',
    description: 'Write an XML sidecar (.nfo) next to every downloaded or translated subtitle. Contains provider, language, score, and translation metadata. Off by default.',
    advanced: true },
  // Automation — Web Player
  { key: 'streaming_enabled', label: 'Enable Video Streaming', type: 'toggle', tab: 'Automation',
    description: 'Serve video files for in-browser preview. Disable to block the /media/stream endpoint.',
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
