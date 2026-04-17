import { api } from './core'
import type { HealthStatus, UpdateInfo, Stats } from '@/lib/types'

// ─── Health & Status ─────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await api.get('/health')
  return data
}

export async function getUpdateInfo(): Promise<UpdateInfo> {
  const { data } = await api.get('/update')
  return data
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get('/stats')
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
