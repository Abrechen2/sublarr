/**
 * Help text for all settings fields, keyed by FieldConfig.key.
 * Used by SettingRow / InfoTooltip throughout the Settings page.
 */
export const HELP_TEXT: Record<string, string> = {
  // General
  port: 'TCP port Sublarr listens on. Default: 5765. Requires restart.',
  api_key: 'Protects all API endpoints. Leave empty to disable authentication.',
  log_level: 'Verbosity of server logs. Options: DEBUG, INFO, WARNING, ERROR.',
  media_path: 'Root path to your media library. Used for subtitle file writing.',
  db_path: 'Path to the SQLite database file.',

  // Translation
  source_language: 'BCP-47 language code of the original subtitles (e.g. "en").',
  target_language: 'BCP-47 language code to translate into (e.g. "de").',
  source_language_name: 'Human-readable name for the source language (e.g. "English").',
  target_language_name: 'Human-readable name for the target language (e.g. "German").',
  hi_removal_enabled: 'Strip hearing-impaired tags like [applause] or (music) from subtitles.',

  // Automation — Upgrade
  upgrade_enabled: 'Automatically replace SRT subtitles with better ASS versions when found.',
  upgrade_prefer_ass: 'Prioritize ASS-format subtitles. ASS gets a +50 scoring bonus.',
  upgrade_min_score_delta: 'Minimum score improvement required before upgrading a subtitle.',
  upgrade_window_days: 'Only upgrade subtitles found within this many days of original download.',

  // Automation — Webhook
  webhook_delay_minutes: 'Wait this many minutes after a Sonarr/Radarr event before processing.',
  webhook_auto_scan: 'Scan media for missing subtitles after download events.',
  webhook_auto_search: 'Search providers for missing subtitles after download events.',
  webhook_auto_translate: 'Translate downloaded subtitles to the target language automatically.',

  // Automation — Search Scheduler
  wanted_search_interval_hours: 'How often to search providers for wanted items. 0 = disabled.',
  wanted_search_on_startup: 'Run a provider search when Sublarr starts.',
  wanted_search_max_items_per_run: 'Limit provider searches per scheduler run to avoid rate limits.',

  // Wanted
  wanted_scan_interval_hours: 'How often to scan media for missing subtitles. 0 = disabled.',
  wanted_anime_only: 'Only add Sonarr series tagged as anime to the Wanted list.',
  wanted_anime_movies_only: 'Only add Radarr movies tagged as anime to the Wanted list.',
  wanted_scan_on_startup: 'Scan for missing subtitles when Sublarr starts.',
  wanted_auto_extract: 'When scanner detects embedded ASS/SRT streams, extract them automatically.',
  wanted_auto_translate: 'Immediately translate extracted subtitle (requires auto-extract enabled).',
  wanted_max_search_attempts: 'Give up searching for a subtitle after this many failed attempts.',

  // Sonarr
  sonarr_url: 'Full URL to Sonarr including port (e.g. http://localhost:8989).',
  sonarr_api_key: 'API key from Sonarr → Settings → General → Security.',

  // Radarr
  radarr_url: 'Full URL to Radarr including port (e.g. http://localhost:7878).',
  radarr_api_key: 'API key from Radarr → Settings → General → Security.',

  // Library Sources (Standalone Mode)
  standalone_enabled: 'Enable direct filesystem scanning without Sonarr/Radarr.',
  tmdb_api_key: 'TMDB Bearer Token for movie/series metadata in standalone mode.',
  tvdb_api_key: 'Optional TVDB API key for enhanced TV series metadata.',
  tvdb_pin: 'Optional TVDB subscriber PIN.',
  standalone_scan_interval_hours: 'How often to scan watched folders for new files. 0 = disabled.',
  standalone_debounce_seconds: 'Wait this many seconds after file detection before processing.',

  // Translation Backends
  ollama_url: 'Full URL to your Ollama instance (e.g. http://localhost:11434).',
  ollama_model: 'Ollama model to use for translation (e.g. qwen2.5:7b).',
  ollama_timeout: 'Seconds to wait for Ollama to respond before giving up.',
  deepl_api_key: 'DeepL API authentication key. Get it at deepl.com/pro-api.',
  deepl_formality: 'Preferred translation formality. Options: default, more, less.',
  openai_api_key: 'OpenAI API key for GPT-based translation.',
  openai_model: 'OpenAI model name (e.g. gpt-4o-mini).',
  openai_base_url: 'Custom OpenAI-compatible API base URL for self-hosted models.',
  translation_backend: 'Which translation engine to use: ollama, deepl, or openai.',
  translation_batch_size: 'Number of subtitle lines to send per translation request.',
  translation_max_retries: 'Retry failed translation requests this many times.',

  // Media Servers
  jellyfin_url: 'Full URL to Jellyfin (e.g. http://localhost:8096).',
  jellyfin_api_key: 'API key from Jellyfin → Dashboard → API Keys.',
  jellyfin_enabled: 'Trigger Jellyfin library refresh after subtitle download.',
  emby_url: 'Full URL to Emby (e.g. http://localhost:8096).',
  emby_api_key: 'API key from Emby → Settings → API Keys.',
  emby_enabled: 'Trigger Emby library refresh after subtitle download.',
  plex_url: 'Full URL to Plex (e.g. http://localhost:32400).',
  plex_token: 'Plex authentication token. Found in Plex account settings.',
  plex_enabled: 'Trigger Plex library refresh after subtitle download.',

  // Providers
  animetosho_enabled: 'Enable AnimeTosho subtitle provider.',
  jimaku_enabled: 'Enable Jimaku subtitle provider (anime-specific, requires API key).',
  jimaku_api_key: 'API key from jimaku.cc account settings.',
  opensubtitles_enabled: 'Enable OpenSubtitles provider (requires API key).',
  opensubtitles_api_key: 'API key from opensubtitles.com developer settings.',
  opensubtitles_username: 'OpenSubtitles account username.',
  opensubtitles_password: 'OpenSubtitles account password.',
  subdl_enabled: 'Enable SubDL provider (requires API key, 2000 downloads/day).',
  subdl_api_key: 'API key from subdl.com account settings.',

  // Scoring
  score_hash_match: 'Bonus score for hash-matched subtitles (exact file match).',
  score_series_match: 'Score for matching series name.',
  score_year_match: 'Score for matching release year.',
  score_season_match: 'Score for matching season number.',
  score_episode_match: 'Score for matching episode number.',
  score_release_group: 'Score for matching release group name.',
  score_ass_bonus: 'Extra score added to ASS-format subtitles.',

  // Events & Hooks
  hooks_enabled: 'Enable custom script hooks for subtitle events.',
  hook_on_download: 'Shell command to run after a subtitle is downloaded.',
  hook_on_translate: 'Shell command to run after a subtitle is translated.',
  hook_on_upgrade: 'Shell command to run after a subtitle is upgraded.',

  // Backup
  backup_enabled: 'Automatically back up the SQLite database on a schedule.',
  backup_interval_hours: 'How often to create a database backup. 0 = disabled.',
  backup_keep_count: 'Number of backup files to retain before deleting the oldest.',
  backup_path: 'Directory where backup files are stored.',

  // Subtitle Tools
  hi_removal_aggressive: 'Also remove lines that are entirely in brackets, not just tagged text.',
  ass_style_threshold: 'Percentage of positioned lines (\\pos/\\move) above which a style is treated as Signs/Songs and skipped for translation.',

  // Cleanup
  cleanup_enabled: 'Automatically remove orphaned subtitle files on a schedule.',
  cleanup_interval_hours: 'How often to run the cleanup job. 0 = disabled.',
  cleanup_dry_run: 'Preview what would be deleted without actually removing files.',

  // Integrations
  discord_webhook_url: 'Discord webhook URL for status notifications.',
  slack_webhook_url: 'Slack webhook URL for status notifications.',
  ntfy_url: 'ntfy topic URL for push notifications.',
  apprise_urls: 'Comma-separated Apprise notification URLs.',
  notifications_enabled: 'Send notifications on subtitle downloads, failures, and upgrades.',
  notify_on_download: 'Send a notification when a subtitle is successfully downloaded.',
  notify_on_error: 'Send a notification when a subtitle download or translation fails.',
  notify_on_upgrade: 'Send a notification when a subtitle is upgraded.',

  // Whisper
  whisper_enabled: 'Enable Whisper-based subtitle extraction from audio/video.',
  whisper_model: 'Whisper model size: tiny, base, small, medium, large.',
  whisper_device: 'Compute device for Whisper: cpu or cuda.',
  whisper_language: 'Force Whisper to detect this language (leave empty for auto-detect).',
  whisper_timeout: 'Seconds to wait for Whisper transcription before giving up.',
}
