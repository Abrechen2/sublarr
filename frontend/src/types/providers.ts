/** Subtitle provider types. */

import type { BackendConfigField } from './translation'

export interface ProviderConfigField {
  key: string
  label: string
  type: 'text' | 'password'
  required: boolean
}

export interface ProviderHealthStats {
  total_searches: number
  /** Searches where the provider returned ≥1 usable result (since 0.92.0-beta). */
  successful_searches: number
  successful_downloads: number
  failed_downloads: number
  /**
   * @deprecated Alias for download_rate (downloads / total_searches). Kept for
   * backwards-compat with older clients; new code should read download_rate
   * + result_rate instead.
   */
  success_rate: number
  /** successful_downloads / total_searches — what we actually picked. */
  download_rate: number
  /** successful_searches / total_searches — what providers offered (since 0.92.0-beta). */
  result_rate: number
  avg_score: number
  consecutive_failures: number
  last_success_at: string | null
  last_failure_at: string | null
  avg_response_time_ms: number
  last_response_time_ms: number
  auto_disabled: boolean
  disabled_until: string
}

export interface ProviderInfo {
  name: string
  enabled: boolean
  initialized: boolean
  healthy: boolean
  message: string
  priority: number
  downloads: number
  config_fields: ProviderConfigField[]
  /** ISO 639-1 codes the provider declares support for (since 1.12.2, #192). */
  languages?: string[]
  stats: ProviderHealthStats
  /**
   * Machine-readable reason behind `healthy` (#201). Branch on this rather
   * than on `message`, which is free text meant for a human to read.
   * Mirrors STATUS_REASONS in backend/providers/manager_status_mixin.py —
   * a value added there needs its label here or it renders blank.
   */
  status_reason?: ProviderStatusReason
  /** Share of all downloads across every provider, 0..1 (#200). */
  contribution_share?: number
  /**
   * Has this provider ever produced a download? `null`/undefined means "not
   * enough evidence yet" — a provider added yesterday has contributed nothing
   * either, and flagging it would train the reader to ignore the flag.
   */
  earns_its_place?: boolean | null
  // Sent by the /providers status endpoint for initialized providers.
  circuit_breaker_state?: string
  throttled_until?: string
  throttle_reason?: string
}

export type ProviderStatusReason =
  | 'ok'
  | 'auto_disabled'
  | 'circuit_open'
  | 'consecutive_failures'
  | 'credentials_rejected'
  | 'host_unreachable'
  | 'no_results'
  | 'no_credentials'
  | 'not_initialized'

export interface ProviderHealthItem {
  name: string
  healthy: boolean
  enabled: boolean
  initialized: boolean
  success_rate: number
  download_rate?: number
  result_rate?: number
  avg_response_time_ms: number
  last_response_time_ms: number
  auto_disabled: boolean
  disabled_until: string
  consecutive_failures: number
  total_searches: number
  circuit_breaker_state: string
  throttled_until: string | null
  throttle_reason: string | null
  /**
   * Kept apart because search and download use different credentials and fail
   * independently — a provider can pass every search while its download path
   * is dead, and a signal built on searches alone shows green straight through
   * that.
   */
  last_search_at: string | null
  last_download_at: string | null
  /**
   * The one gate currently keeping this provider out of searches, resolved in
   * the order the search path applies them. 'ok' when nothing is blocking.
   */
  gate:
    | 'ok'
    | 'auto_disabled'
    | 'circuit_open'
    | 'rate_limited'
    | 'budget_exhausted'
    | 'no_pool_key'
    | 'not_initialised'
}

export interface ProviderStats {
  cache: Record<string, { total: number; active: number }>
  downloads: Record<string, { total: number; by_format: Record<string, number> }>
  performance: Record<string, ProviderHealthStats & { success_rate: number; auto_disabled: boolean }>
}

// ─── Media Servers ──────────────────────────────────────────────────────────

export interface MediaServerType {
  name: string           // "jellyfin", "plex", "kodi"
  display_name: string   // "Jellyfin / Emby", "Plex", "Kodi"
  config_fields: BackendConfigField[]
}

export interface MediaServerInstance {
  type: string           // "jellyfin", "plex", "kodi"
  name: string           // User-defined name
  enabled: boolean
  [key: string]: unknown // Dynamic config keys
}

export interface MediaServerHealthResult {
  name: string
  type: string
  healthy: boolean
  message: string
}

export interface MediaServerTestResult {
  healthy: boolean
  message: string
}
