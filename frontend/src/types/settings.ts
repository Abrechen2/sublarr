/** Settings / config types — profiles, hooks, webhooks, scoring. */

export interface LanguageProfile {
  id: number
  name: string
  source_language: string
  source_language_name: string
  target_languages: string[]
  target_language_names: string[]
  is_default: boolean
  translation_backend: string
  fallback_chain: string[]
  forced_preference: 'disabled' | 'separate' | 'auto'
  hi_preference: 'include' | 'prefer' | 'exclude' | 'only'
}

// ─── Events & Hooks ──────────────────────────────────────────────────────────

export interface EventCatalogItem {
  name: string
  label: string
  description: string
  payload_keys: string[]
}

export interface HookConfig {
  id: number
  name: string
  event_name: string
  hook_type: string
  enabled: boolean
  script_path: string
  timeout_seconds: number
  last_triggered_at: string
  last_status: string
  trigger_count: number
  created_at: string
  updated_at: string
}

export interface WebhookConfig {
  id: number
  name: string
  event_name: string
  url: string
  secret: string
  enabled: boolean
  retry_count: number
  timeout_seconds: number
  last_triggered_at: string
  last_status_code: number
  last_error: string
  consecutive_failures: number
  trigger_count: number
  created_at: string
  updated_at: string
}

export interface HookLog {
  id: number
  hook_id: number | null
  webhook_id: number | null
  event_name: string
  hook_type: string
  success: boolean
  exit_code: number | null
  status_code: number | null
  stdout: string
  stderr: string
  error: string
  duration_ms: number
  triggered_at: string
}

export interface HookTestResult {
  success: boolean
  exit_code?: number
  stdout?: string
  stderr?: string
  status_code?: number
  error?: string
  duration_ms: number
}

// ─── Scoring ─────────────────────────────────────────────────────────────────

export interface ScoringWeights {
  episode: Record<string, number>
  movie: Record<string, number>
  defaults: {
    episode: Record<string, number>
    movie: Record<string, number>
  }
}

export interface ProviderModifiers {
  [provider_name: string]: number
}

export interface ScoringPresetMeta {
  name: string
  description: string
  type: 'episode' | 'movie' | 'both'
}

export interface ScoringPreset extends ScoringPresetMeta {
  weights: {
    episode?: Record<string, number>
    movie?: Record<string, number>
  }
  provider_modifiers: Record<string, number>
}

// ─── API Keys ────────────────────────────────────────────────────────────────

export interface ApiKeyService {
  service: string
  keys: { name: string; status: 'configured' | 'missing'; masked_value: string }[]
  testable: boolean
}

export interface ApiKeyExportData {
  config: Record<string, string>
  profiles: unknown[]
  glossary: unknown[]
}

export interface BazarrMigrationPreview {
  config_entries: { key: string; value: string; current_value: string }[]
  profiles: unknown[]
  blacklist_count: number
  warnings: string[]
}
