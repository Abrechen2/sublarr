import { api } from '../core'
import type { PaginatedBlacklist, PaginatedHistory, HistoryStats } from '@/lib/types'

// ─── Blacklist ────────────────────────────────────────────────────────────────

export async function getBlacklist(page = 1, perPage = 50): Promise<PaginatedBlacklist> {
  const { data } = await api.get('/blacklist', { params: { page, per_page: perPage } })
  return data
}

export async function addToBlacklist(entry: {
  provider_name: string; subtitle_id: string;
  language?: string; file_path?: string; title?: string; reason?: string
}): Promise<{ status: string; id: number }> {
  const { data } = await api.post('/blacklist', entry)
  return data
}

export async function removeFromBlacklist(id: number): Promise<void> {
  await api.delete(`/blacklist/${id}`)
}

export async function clearBlacklist(): Promise<{ status: string; count: number }> {
  const { data } = await api.delete('/blacklist', { params: { confirm: 'true' } })
  return data
}

// ─── History ──────────────────────────────────────────────────────────────────

export async function getHistory(
  page = 1, perPage = 50, provider?: string, language?: string
): Promise<PaginatedHistory> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (provider) params.provider = provider
  if (language) params.language = language
  const { data } = await api.get('/history', { params })
  return data
}

export async function getHistoryStats(): Promise<HistoryStats> {
  const { data } = await api.get('/history/stats')
  return data
}
