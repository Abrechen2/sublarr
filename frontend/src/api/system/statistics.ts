/** Grouped analytics API (V1.6 #9) — /api/v1/statistics/<group>. */
import { api } from '../core'

export type StatRange = '24h' | '7d' | '30d' | 'all'

export interface SubtitlesStats {
  range: string
  total: number
  by_source: Record<string, number>
  by_provider: Record<string, number>
  by_language: Record<string, number>
  avg_score: number
}

export interface TranslationStats {
  range: string
  total: number
  by_backend: Record<string, number>
  total_chars: number
  total_cost_micro_usd: number
  avg_latency_ms: number
  pass_rate: number
  mt_awaiting_original: number
}

export interface ProviderStatRow {
  provider: string
  searches: number
  hit_rate: number
  downloads: number
  failures: number
  avg_score: number
  avg_response_ms: number
  auto_disabled: boolean
}

export interface SystemStats {
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  uptime_seconds: number
  db_size_bytes: number
  scheduler_runs: { job_id: string; status: string; duration_ms: number }[]
}

export interface LibraryStats {
  subtitle_files: number
  languages: string[]
  wanted_items: number
}

export interface TrendsStats {
  range: string
  dates: string[]
  downloads: number[]
  translations: number[]
  syncs: number[]
}

export async function getSubtitlesStats(range: StatRange): Promise<SubtitlesStats> {
  const { data } = await api.get('/statistics/subtitles', { params: { range } })
  return data
}

export async function getTranslationStats(range: StatRange): Promise<TranslationStats> {
  const { data } = await api.get('/statistics/translation', { params: { range } })
  return data
}

export async function getProvidersStats(): Promise<{ providers: ProviderStatRow[] }> {
  const { data } = await api.get('/statistics/providers')
  return data
}

export async function getSystemStats(): Promise<SystemStats> {
  const { data } = await api.get('/statistics/system')
  return data
}

export async function getLibraryStats(): Promise<LibraryStats> {
  const { data } = await api.get('/statistics/library')
  return data
}

export async function getTrendsStats(range: StatRange): Promise<TrendsStats> {
  const { data } = await api.get('/statistics/trends', { params: { range } })
  return data
}
