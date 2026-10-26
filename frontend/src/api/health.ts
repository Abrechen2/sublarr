import { api } from './core'
import type { HealthStatus, UpdateInfo, Stats } from '@/lib/types'

// ─── Health & Status ─────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await api.get('/health')
  return data
}

/**
 * The update check is a best-effort background poll that the backend
 * rate-limits, so a 429 is an expected answer, not an error: resolve it as
 * "no information" (null) instead of rejecting, so React Query neither
 * retries nor surfaces it as a failed query.
 */
export async function getUpdateInfo(): Promise<UpdateInfo | null> {
  const response = await api.get<UpdateInfo>('/update', {
    validateStatus: (status) => (status >= 200 && status < 300) || status === 429,
  })
  if (response.status === 429) return null
  return response.data
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get('/stats')
  return data
}

// ─── Detailed Health (per-subsystem) ─────────────────────────────────────────

export interface ArrInstanceCheck {
  instance_name: string
  healthy: boolean
  message: string
}

export interface MediaServerCheck {
  type: string
  name: string
  healthy: boolean
  message: string
}

export interface DetailedSubsystem {
  healthy: boolean
  message?: string
  backend?: string
  size_bytes?: number
  wal_mode?: boolean
  percent?: number
  free_bytes?: number
  sonarr?: ArrInstanceCheck[]
  radarr?: ArrInstanceCheck[]
  instances?: MediaServerCheck[]
  backends?: Record<string, { healthy: boolean; message: string }>
  active_backend?: string | null
}

export interface DetailedHealth {
  /** 'unhealthy' when the schema is not at the migration head (as on /health). */
  status: 'healthy' | 'degraded' | 'unhealthy'
  subsystems: Record<string, DetailedSubsystem>
}

export async function getDetailedHealth(): Promise<DetailedHealth> {
  // 503 is a valid, fully-populated "degraded"/"unhealthy" response — don't treat it as
  // an error or the dev-mock interceptor would swallow the real payload.
  const { data } = await api.get('/health/detailed', {
    validateStatus: (s) => s === 200 || s === 503,
  })
  return data
}

// ─── Budget State ────────────────────────────────────────────────────────────

export interface BudgetWindow {
  second: number
  hour: number
  day: number
}

export interface ProviderBudgetLearning {
  adjustment_factor: number
  consecutive_good_days: number
  last_429_at: string | null
}

export interface ProviderBudgetKey {
  id: number
  label: string
  tier: string
  used: { second: number; hour: number; day: number }
  limit: { second: number; hour: number; day: number }
  last_429_at: string | null
  last_used_at: string | null
}

export interface ProviderBudget {
  name: string
  tier: string
  limits: BudgetWindow
  usage: BudgetWindow
  reset_seconds: BudgetWindow
  learning?: ProviderBudgetLearning | null
  keys?: ProviderBudgetKey[]
}

export interface BudgetResponse {
  enabled: boolean
  providers: ProviderBudget[]
}

export async function getBudgetState(): Promise<BudgetResponse> {
  const { data } = await api.get('/system/budget')
  return data
}

// ─── First-run Setup Wizard ──────────────────────────────────────────────────

export type SetupProfile = 'light' | 'balanced' | 'aggressive'

export interface SetupBenchmark {
  cpu_count: number
  ram_gb: number
  recommended_profile: SetupProfile
}

export interface SetupStatus {
  wizard_completed: boolean
  benchmark: SetupBenchmark
}

export interface CompleteSetupResult {
  ok: boolean
  profile: SetupProfile
  applied: Record<string, number | string | boolean>
}

export async function getSetupStatus(): Promise<SetupStatus> {
  const { data } = await api.get('/system/setup/status')
  return data
}

export async function completeSetup(profile: SetupProfile): Promise<CompleteSetupResult> {
  const { data } = await api.post('/system/setup/complete', { profile })
  return data
}
