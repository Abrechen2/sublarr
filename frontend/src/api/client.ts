import axios from 'axios'
import type {
  HealthStatus, Stats, PaginatedJobs, Job, BatchState,
  LibraryInfo, AppConfig, PaginatedWanted, WantedSummary,
  WantedSearchResponse, WantedBatchStatus, ProviderInfo, ProviderStats,
  RetranslateStatus, LanguageProfile,
} from '@/lib/types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Add API key interceptor if configured
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('sublarr_api_key')
  if (apiKey) {
    config.headers['X-Api-Key'] = apiKey
  }
  return config
})

// ─── Health & Status ─────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await api.get('/health')
  return data
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get('/stats')
  return data
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export async function getJobs(page = 1, perPage = 50, status?: string): Promise<PaginatedJobs> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (status) params.status = status
  const { data } = await api.get('/jobs', { params })
  return data
}

export async function getJobStatus(jobId: string): Promise<Job> {
  const { data } = await api.get(`/status/${jobId}`)
  return data
}

// ─── Translation ─────────────────────────────────────────────────────────────

export async function translateFile(filePath: string, force = false) {
  const { data } = await api.post('/translate', { file_path: filePath, force })
  return data
}

export async function translateSync(filePath: string, force = false) {
  const { data } = await api.post('/translate/sync', { file_path: filePath, force })
  return data
}

// ─── Batch ───────────────────────────────────────────────────────────────────

export async function startBatch(directory: string, force = false, dryRun = false) {
  const { data } = await api.post('/batch', { directory, force, dry_run: dryRun })
  return data
}

export async function getBatchStatus(): Promise<BatchState> {
  const { data } = await api.get('/batch/status')
  return data
}

// ─── Config ──────────────────────────────────────────────────────────────────

export async function getConfig(): Promise<AppConfig> {
  const { data } = await api.get('/config')
  return data
}

export async function updateConfig(values: Record<string, unknown>) {
  const { data } = await api.put('/config', values)
  return data
}

// ─── Wanted ─────────────────────────────────────────────────────────────

export async function getWantedItems(
  page = 1, perPage = 50, itemType?: string, status?: string
): Promise<PaginatedWanted> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (itemType) params.item_type = itemType
  if (status) params.status = status
  const { data } = await api.get('/wanted', { params })
  return data
}

export async function getWantedSummary(): Promise<WantedSummary> {
  const { data } = await api.get('/wanted/summary')
  return data
}

export async function refreshWanted(seriesId?: number) {
  const body = seriesId ? { series_id: seriesId } : {}
  const { data } = await api.post('/wanted/refresh', body)
  return data
}

export async function updateWantedItemStatus(itemId: number, status: string) {
  const { data } = await api.put(`/wanted/${itemId}/status`, { status })
  return data
}

export async function deleteWantedItem(itemId: number) {
  const { data } = await api.delete(`/wanted/${itemId}`)
  return data
}

export async function searchWantedItem(itemId: number): Promise<WantedSearchResponse> {
  const { data } = await api.post(`/wanted/${itemId}/search`)
  return data
}

export async function processWantedItem(itemId: number): Promise<{ status: string }> {
  const { data } = await api.post(`/wanted/${itemId}/process`)
  return data
}

export async function startWantedBatchSearch(itemIds?: number[]): Promise<{ status: string; total_items: number }> {
  const body = itemIds ? { item_ids: itemIds } : {}
  const { data } = await api.post('/wanted/batch-search', body)
  return data
}

export async function getWantedBatchStatus(): Promise<WantedBatchStatus> {
  const { data } = await api.get('/wanted/batch-search/status')
  return data
}

export async function searchAllWanted(): Promise<{ status: string }> {
  const { data } = await api.post('/wanted/search-all')
  return data
}

// ─── Providers ───────────────────────────────────────────────────────────────

export async function getProviders(): Promise<{ providers: ProviderInfo[] }> {
  const { data } = await api.get('/providers')
  return data
}

export async function testProvider(name: string): Promise<{ provider: string; healthy: boolean; message: string }> {
  const { data } = await api.post(`/providers/test/${name}`)
  return data
}

export async function getProviderStats(): Promise<ProviderStats> {
  const { data } = await api.get('/providers/stats')
  return data
}

export async function clearProviderCache(providerName?: string) {
  const body = providerName ? { provider_name: providerName } : {}
  const { data } = await api.post('/providers/cache/clear', body)
  return data
}

// ─── Language Profiles ───────────────────────────────────────────────────────

export async function getLanguageProfiles(): Promise<LanguageProfile[]> {
  const { data } = await api.get('/language-profiles')
  return data.profiles
}

export async function createLanguageProfile(profile: Omit<LanguageProfile, 'id' | 'is_default'>): Promise<LanguageProfile> {
  const { data } = await api.post('/language-profiles', profile)
  return data
}

export async function updateLanguageProfile(id: number, profile: Partial<LanguageProfile>): Promise<LanguageProfile> {
  const { data } = await api.put(`/language-profiles/${id}`, profile)
  return data
}

export async function deleteLanguageProfile(id: number): Promise<void> {
  await api.delete(`/language-profiles/${id}`)
}

export async function assignProfile(type: 'series' | 'movie', arrId: number, profileId: number): Promise<void> {
  await api.put('/language-profiles/assign', { type, arr_id: arrId, profile_id: profileId })
}

// ─── Re-Translation ──────────────────────────────────────────────────────────

export async function getRetranslateStatus(): Promise<RetranslateStatus> {
  const { data } = await api.get('/retranslate/status')
  return data
}

export async function retranslateSingle(itemId: number): Promise<{ status: string; job_id: string }> {
  const { data } = await api.post(`/retranslate/${itemId}`)
  return data
}

export async function retranslateBatch(): Promise<{ status: string; total: number }> {
  const { data } = await api.post('/retranslate/batch')
  return data
}

// ─── Library ─────────────────────────────────────────────────────────────────

export async function getLibrary(): Promise<LibraryInfo> {
  const { data } = await api.get('/library')
  return data
}

// ─── Logs ────────────────────────────────────────────────────────────────────

export async function getLogs(lines = 200, level?: string) {
  const params: Record<string, unknown> = { lines }
  if (level) params.level = level
  const { data } = await api.get('/logs', { params })
  return data
}

export default api
