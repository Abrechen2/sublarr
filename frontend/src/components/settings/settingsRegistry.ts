/**
 * Settings registry — flat index of all settings for search.
 *
 * Each entry maps a human-readable label + keywords to a settings route.
 * Used by SettingsSearch to find settings by keyword.
 */

export interface SettingsEntry {
  readonly id: string
  readonly label: string
  readonly keywords: string[]
  readonly category: string
  readonly route: string
}

export const SETTINGS_REGISTRY: readonly SettingsEntry[] = [
  // General
  { id: 'language', label: 'Interface Language', keywords: ['language', 'locale', 'sprache', 'deutsch', 'english'], category: 'General', route: '/settings/general' },
  { id: 'media-path', label: 'Media Path', keywords: ['media', 'path', 'folder', 'directory', 'pfad'], category: 'General', route: '/settings/general' },
  { id: 'port', label: 'Server Port', keywords: ['port', 'server', 'network'], category: 'General', route: '/settings/general' },
  { id: 'log-level', label: 'Log Level', keywords: ['log', 'level', 'debug', 'info', 'warning', 'error', 'logging'], category: 'General', route: '/settings/general' },
  { id: 'translation-toggle', label: 'Translation Feature', keywords: ['translation', 'translate', 'ai', 'ollama', 'enable', 'disable'], category: 'General', route: '/settings/general' },

  // Connections
  { id: 'sonarr', label: 'Sonarr Connection', keywords: ['sonarr', 'connection', 'api', 'series', 'tv'], category: 'Connections', route: '/settings/connections' },
  { id: 'radarr', label: 'Radarr Connection', keywords: ['radarr', 'connection', 'api', 'movies', 'film'], category: 'Connections', route: '/settings/connections' },
  { id: 'media-servers', label: 'Media Servers', keywords: ['plex', 'jellyfin', 'emby', 'media', 'server'], category: 'Connections', route: '/settings/connections' },
  { id: 'api-keys', label: 'API Keys', keywords: ['api', 'key', 'token', 'authentication'], category: 'Connections', route: '/settings/connections' },

  // Subtitles
  { id: 'scoring', label: 'Subtitle Scoring', keywords: ['score', 'scoring', 'weight', 'rank', 'quality'], category: 'Subtitles', route: '/settings/subtitles' },
  { id: 'format', label: 'Subtitle Format', keywords: ['format', 'ass', 'srt', 'vtt', 'convert'], category: 'Subtitles', route: '/settings/subtitles' },
  { id: 'cleanup', label: 'Subtitle Cleanup', keywords: ['cleanup', 'clean', 'deduplicate', 'orphan', 'remove'], category: 'Subtitles', route: '/settings/subtitles' },
  { id: 'embedded', label: 'Embedded Extraction', keywords: ['embedded', 'extract', 'mkv', 'video', 'track'], category: 'Subtitles', route: '/settings/subtitles' },
  { id: 'language-profiles', label: 'Language Profiles', keywords: ['language', 'profile', 'target', 'source'], category: 'Subtitles', route: '/settings/subtitles' },
  { id: 'fansub', label: 'Fansub Preferences', keywords: ['fansub', 'group', 'prefer', 'exclude'], category: 'Subtitles', route: '/settings/subtitles' },

  // Providers
  { id: 'providers', label: 'Subtitle Providers', keywords: ['provider', 'source', 'opensubtitles', 'jimaku', 'subdl', 'animetosho'], category: 'Providers', route: '/settings/providers' },
  { id: 'marketplace', label: 'Provider Marketplace', keywords: ['marketplace', 'install', 'add', 'plugin'], category: 'Providers', route: '/settings/providers' },
  { id: 'anti-captcha', label: 'Anti-Captcha', keywords: ['captcha', 'anti-captcha', 'solver'], category: 'Providers', route: '/settings/providers' },

  // Automation
  { id: 'wanted-search', label: 'Wanted Search', keywords: ['wanted', 'search', 'frequency', 'interval', 'scan'], category: 'Automation', route: '/settings/automation' },
  { id: 'auto-upgrade', label: 'Auto Upgrade', keywords: ['upgrade', 'auto', 'threshold', 'improve', 'better'], category: 'Automation', route: '/settings/automation' },
  { id: 'processing', label: 'Processing Pipeline', keywords: ['processing', 'pipeline', 'auto-translate', 'auto-sync', 'auto-cleanup'], category: 'Automation', route: '/settings/automation' },
  { id: 'scheduled-tasks', label: 'Scheduled Tasks', keywords: ['schedule', 'task', 'cron', 'timer', 'job'], category: 'Automation', route: '/settings/automation' },

  // Translation
  { id: 'backends', label: 'Translation Backends', keywords: ['backend', 'ollama', 'model', 'ai', 'llm'], category: 'Translation', route: '/settings/translation' },
  { id: 'prompts', label: 'Prompt Presets', keywords: ['prompt', 'preset', 'template', 'instruction'], category: 'Translation', route: '/settings/translation' },
  { id: 'glossary', label: 'Global Glossary', keywords: ['glossary', 'term', 'dictionary', 'translation'], category: 'Translation', route: '/settings/translation' },
  { id: 'whisper', label: 'Whisper (Speech-to-Text)', keywords: ['whisper', 'speech', 'stt', 'transcribe', 'audio'], category: 'Translation', route: '/settings/translation' },

  // Notifications
  { id: 'notification-channels', label: 'Notification Channels', keywords: ['notification', 'channel', 'webhook', 'discord', 'telegram'], category: 'Notifications', route: '/settings/notifications' },
  { id: 'events-hooks', label: 'Events & Hooks', keywords: ['event', 'hook', 'trigger', 'webhook', 'callback'], category: 'Notifications', route: '/settings/notifications' },
  { id: 'quiet-hours', label: 'Quiet Hours', keywords: ['quiet', 'hours', 'silence', 'mute', 'schedule'], category: 'Notifications', route: '/settings/notifications' },

  // System
  { id: 'security', label: 'Security', keywords: ['security', 'password', 'auth', 'authentication', 'login'], category: 'System', route: '/settings/system' },
  { id: 'backup', label: 'Backup & Restore', keywords: ['backup', 'restore', 'export', 'import', 'save'], category: 'System', route: '/settings/system' },
  { id: 'logs', label: 'Log Viewer', keywords: ['log', 'viewer', 'protokoll', 'support', 'bundle'], category: 'System', route: '/settings/system' },
  { id: 'integrations', label: 'Integrations', keywords: ['integration', 'bazarr', 'compatibility', 'health', 'diagnostics'], category: 'System', route: '/settings/system' },
  { id: 'migration', label: 'Migration', keywords: ['migration', 'bazarr', 'import', 'wizard'], category: 'System', route: '/settings/system' },
]

/**
 * Search the settings registry by query string.
 * Matches against label and keywords (case-insensitive).
 */
export function searchSettings(query: string): readonly SettingsEntry[] {
  if (!query.trim()) return []

  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)

  return SETTINGS_REGISTRY.filter((entry) => {
    const searchable = [entry.label.toLowerCase(), ...entry.keywords]
    return terms.every((term) => searchable.some((s) => s.includes(term)))
  })
}
