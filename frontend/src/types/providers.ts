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
  stats: ProviderHealthStats
  // Sent by the /providers status endpoint for initialized providers.
  circuit_breaker_state?: string
  throttled_until?: string
  throttle_reason?: string
}

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
