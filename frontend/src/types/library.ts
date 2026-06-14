/** Library types — series, movies, episodes, tracks, sidecars. */

export interface WantedEpisode {
  series_title: string
  episode_number: string
  episode_title: string
  sonarr_series_id: number
  sonarr_episode_id: number
  path: string
  missing_subtitles: string[]
}

export interface LibraryInfo {
  series: SeriesInfo[]
  movies: MovieInfo[]
}

export interface SeriesInfo {
  id: number
  title: string
  year: number
  seasons: number
  episodes: number
  episodes_with_files: number
  path: string
  poster: string
  status: string
  profile_id: number | null
  profile_name: string
  missing_count: number
  // "sonarr" | "standalone" — present in mixed-mode library responses.
  source?: string
}


export interface MovieInfo {
  id: number
  title: string
  year: number
  has_file: boolean
  path: string
  poster: string
  status: string
  // Sent by the standalone branch of the library list response.
  missing_count?: number
  // "radarr" | "standalone" — present in mixed-mode library responses.
  source?: string
}

export interface EpisodeInfo {
  id: number
  season: number
  episode: number
  title: string
  has_file: boolean
  file_path: string
  subtitles: Record<string, string>  // lang -> "ass"|"srt"|""
  subtitle_scores?: Record<string, number | null>    // lang -> download score (0-100) or null
  subtitle_providers?: Record<string, string | null> // lang -> provider name or null
  audio_languages: string[]
  monitored: boolean
}

export interface SeriesDetail {
  id: number
  title: string
  year: number
  path: string
  poster: string
  fanart: string
  overview: string
  status: string
  season_count: number
  episode_count: number
  episode_file_count: number
  tags: string[]
  profile_name: string
  profile_id: number | null
  target_languages: string[]
  target_language_names: string[]
  source_language: string
  source_language_name: string
  episodes: EpisodeInfo[]
  absolute_order?: boolean
  // 0.71.1: per-series foreign-track cleanup override.
  //   cleanup_foreign_tracks_override: raw SeriesSettings value (null = inherit).
  //   cleanup_foreign_tracks_effective: resolved policy after applying global default.
  cleanup_foreign_tracks_override?: boolean | null
  cleanup_foreign_tracks_effective?: boolean
}

export interface EpisodeHistoryEntry {
  action: 'download' | 'translate'
  provider_name: string
  format: string
  score: number
  date: string
  status: string
  error: string
}

// ─── Subtitle Sidecar Management ─────────────────────────────────────────────

export type SubtitleModifier = 'hi' | 'forced' | 'sdh' | 'cc'

export interface SidecarSubtitle {
  path: string
  language: string      // e.g. "de", "en", "ja"
  format: string        // "ass" | "srt" | "vtt" | "ssa"
  size_bytes: number
  modified_at: number   // Unix timestamp (seconds)
  // Optional secondary tag from the filename (e.g. "ep.en.hi.srt" -> "hi").
  // Backend strips "bak" before reaching the UI; only user-visible modifiers
  // (hi/forced/sdh/cc) appear here.
  modifier?: SubtitleModifier
}

// ─── Subtitle Backups (`.bak.<ext>` files) ───────────────────────────────────

export interface SubtitleBackup {
  path: string
  language: string
  format: string
  // Full modifier stack from the filename, e.g. ["bak"], ["hi", "bak"].
  modifiers: string[]
  size_bytes: number
  modified_at: number
  // Where the file would land if the user restores it (active sidecar path).
  restore_path: string
  // Parent video path (resolves .mkv/.mp4/...) or null if the video is gone.
  video_path: string | null
  // True when neither active sidecar nor parent video exists — safe to purge.
  is_orphan: boolean
  // ISO8601 — when retention-based auto-purge would remove this file.
  // Null when retention=0 (purge disabled).
  expires_at: string | null
}

export interface SubtitleBackupListResponse {
  backups: SubtitleBackup[]
  count: number
  orphan_count: number
  retention_days: number
}

export interface SubtitleBackupCleanupRequest {
  older_than_days?: number
  orphans_only?: boolean
  dry_run?: boolean
  series_path?: string
}

export interface SubtitleBackupCleanupResponse {
  deleted: string[]
  orphans_purged: number
  skipped: number
  errors: string[]
  dry_run: boolean
  note?: string
}

// ─── Track Manifest ───────────────────────────────────────────────────────────

export interface Track {
  index: number
  sub_index: number
  codec_type: 'audio' | 'subtitle'
  codec: string
  language: string
  title: string
  forced: boolean
  default: boolean
}

export interface EpisodeTracksResponse {
  tracks: Track[]
  video_path: string
}

export interface ExtractTrackResult {
  output_path: string
  language: string
  format: string
  track: Track
}

export interface TrackAsSourceResult {
  content: string
  format: string
  language: string
  title: string
}

// ─── Dubtitle detection (A4 / issue #146) ─────────────────────────────────────

export interface DubtitleCandidate {
  sub_index: number
  stream_index: number | null
  language: string
  title: string
  format: string
  is_sdh: boolean
  subtype: 'full' | 'forced' | 'signs'
  cue_count: number
  cue_density: number
  avg_cps: number
  overlap_ratio: number
  tier1_label: 'likely_dubtitle' | 'candidate' | 'signs_forced' | 'sparse'
  audio_score: number | null
  is_dubtitle: boolean
  reason: string
}

export interface DubtitleDetectionResult {
  video_path: string
  dubtitle_sub_index: number | null
  method: 'tier1' | 'tier2' | 'none'
  tier2_ran: boolean
  min_score: number
  message: string
  whisper_fallback_available: boolean
  candidates: DubtitleCandidate[]
}

// ─── Series preferences ───────────────────────────────────────────────────────

export interface SeriesAudioPref {
  series_id: number
  preferred_audio_track_index: number | null
}

export interface SeriesFansubPrefs {
  series_id: number
  preferred_groups: string[]
  excluded_groups: string[]
  bonus: number
}

// ─── Audio ────────────────────────────────────────────────────────────────────

export interface AudioTrackInfo {
  stream_index: number
  language: string
  codec: string
  channels: number
  title: string
}
