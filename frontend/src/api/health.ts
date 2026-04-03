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
