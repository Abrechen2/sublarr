import axios from 'axios'
import type {
  HealthStatus, Stats, PaginatedJobs, Job, BatchState,
  LibraryInfo, SeriesDetail, AppConfig, PaginatedWanted, WantedSummary,
  WantedSearchResponse, WantedBatchStatus, ProviderInfo, ProviderStats,
  RetranslateStatus, LanguageProfile, EpisodeHistoryEntry,
  PaginatedBlacklist, PaginatedHistory, HistoryStats,
  TranslationBackendInfo, BackendConfig, BackendHealthResult, BackendStats,
  MediaServerType, MediaServerInstance, MediaServerTestResult, MediaServerHealthResult,
  WatchedFolder, StandaloneSeries, StandaloneMovie, StandaloneStatus,
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
  page = 1, perPage = 50, itemType?: string, status?: string, subtitleType?: string
): Promise<PaginatedWanted> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (itemType) params.item_type = itemType
  if (status) params.status = status
  if (subtitleType) params.subtitle_type = subtitleType
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

export async function extractEmbeddedSub(itemId: number, options?: { stream_index?: number; target_language?: string }): Promise<{ status: string; output_path: string; format: string; language: string }> {
  const { data } = await api.post(`/wanted/${itemId}/extract`, options)
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

export async function enableProvider(name: string): Promise<{ status: string; provider: string; message: string }> {
  const { data } = await api.post(`/providers/${name}/enable`)
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

// ─── Library ─────────────────────────────────────────────────────────────────

export async function getLibrary(): Promise<LibraryInfo> {
  const { data } = await api.get('/library')
  return data
}

export async function getSeriesDetail(seriesId: number): Promise<SeriesDetail> {
  const { data } = await api.get(`/library/series/${seriesId}`)
  return data
}

// ─── Episode Search & History ─────────────────────────────────────────────────

export async function episodeSearch(episodeId: number): Promise<WantedSearchResponse> {
  const { data } = await api.post(`/episodes/${episodeId}/search`)
  return data
}

export async function episodeHistory(episodeId: number): Promise<{ entries: EpisodeHistoryEntry[] }> {
  const { data } = await api.get(`/episodes/${episodeId}/history`)
  return data
}

// ─── Job Retry ───────────────────────────────────────────────────────────────

export async function retryJob(jobId: string): Promise<{ status: string; job_id: string }> {
  const { data } = await api.post(`/jobs/${jobId}/retry`)
  return data
}

// ─── Config Export/Import ────────────────────────────────────────────────────

export async function exportConfig(): Promise<AppConfig> {
  const { data } = await api.get('/config/export')
  return data
}

export async function importConfig(config: Record<string, unknown>): Promise<{ status: string; imported_keys: string[]; skipped_secrets: string[] }> {
  const { data } = await api.post('/config/import', config)
  return data
}

// ─── Notifications ───────────────────────────────────────────────────────────

export async function testNotification(url?: string): Promise<{ success: boolean; message: string }> {
  const body = url ? { url } : {}
  const { data } = await api.post('/notifications/test', body)
  return data
}

export async function getNotificationStatus(): Promise<{
  configured: boolean
  url_count: number
  events: Record<string, boolean>
}> {
  const { data } = await api.get('/notifications/status')
  return data
}

// ─── Logs ────────────────────────────────────────────────────────────────────

export async function getLogs(lines = 200, level?: string) {
  const params: Record<string, unknown> = { lines }
  if (level) params.level = level
  const { data } = await api.get('/logs', { params })
  return data
}

// ─── Glossary ─────────────────────────────────────────────────────────────────

export interface GlossaryEntry {
  id: number
  series_id: number
  source_term: string
  target_term: string
  notes: string
  created_at: string
  updated_at: string
}

export async function getGlossaryEntries(seriesId: number, query?: string): Promise<{ entries: GlossaryEntry[]; series_id: number }> {
  const params: Record<string, unknown> = { series_id: seriesId }
  if (query) params.query = query
  const { data } = await api.get('/glossary', { params })
  return data
}

export async function createGlossaryEntry(entry: { series_id: number; source_term: string; target_term: string; notes?: string }): Promise<GlossaryEntry> {
  const { data } = await api.post('/glossary', entry)
  return data
}

export async function updateGlossaryEntry(entryId: number, entry: { source_term?: string; target_term?: string; notes?: string }): Promise<GlossaryEntry> {
  const { data } = await api.put(`/glossary/${entryId}`, entry)
  return data
}

export async function deleteGlossaryEntry(entryId: number): Promise<void> {
  await api.delete(`/glossary/${entryId}`)
}

// ─── Prompt Presets ───────────────────────────────────────────────────────────

export interface PromptPreset {
  id: number
  name: string
  prompt_template: string
  is_default: number
  created_at: string
  updated_at: string
}

export async function getPromptPresets(): Promise<{ presets: PromptPreset[] }> {
  const { data } = await api.get('/prompt-presets')
  return data
}

export async function getDefaultPromptPreset(): Promise<PromptPreset> {
  const { data } = await api.get('/prompt-presets/default')
  return data
}

export async function createPromptPreset(preset: { name: string; prompt_template: string; is_default?: boolean }): Promise<PromptPreset> {
  const { data } = await api.post('/prompt-presets', preset)
  return data
}

export async function updatePromptPreset(presetId: number, preset: { name?: string; prompt_template?: string; is_default?: boolean }): Promise<PromptPreset> {
  const { data } = await api.put(`/prompt-presets/${presetId}`, preset)
  return data
}

export async function deletePromptPreset(presetId: number): Promise<void> {
  await api.delete(`/prompt-presets/${presetId}`)
}

// ─── Instances (Multi-Library) ────────────────────────────────────────────────

export interface InstanceConfig {
  name: string
  url: string
  api_key: string
  path_mapping?: string
}

export async function getSonarrInstances(): Promise<InstanceConfig[]> {
  const { data } = await api.get('/sonarr/instances')
  return data
}

export async function getRadarrInstances(): Promise<InstanceConfig[]> {
  const { data } = await api.get('/radarr/instances')
  return data
}

export async function testSonarrInstance(config: { url: string; api_key: string }): Promise<{ healthy: boolean; message: string }> {
  const { data } = await api.post('/sonarr/instances/test', config)
  return data
}

export async function testRadarrInstance(config: { url: string; api_key: string }): Promise<{ healthy: boolean; message: string }> {
  const { data } = await api.post('/radarr/instances/test', config)
  return data
}

// ─── Onboarding ──────────────────────────────────────────────────────────────

export async function getOnboardingStatus(): Promise<{
  completed: boolean
  has_sonarr: boolean
  has_radarr: boolean
  has_ollama: boolean
  has_providers: boolean
}> {
  const { data } = await api.get('/onboarding/status')
  return data
}

export async function completeOnboarding(): Promise<{ status: string }> {
  const { data } = await api.post('/onboarding/complete')
  return data
}

// ─── Translation Backends ────────────────────────────────────────────────────

export async function getBackends(): Promise<{ backends: TranslationBackendInfo[] }> {
  const { data } = await api.get('/backends')
  return data
}

export async function testBackend(name: string): Promise<BackendHealthResult> {
  const { data } = await api.post(`/backends/test/${name}`)
  return data
}

export async function getBackendConfig(name: string): Promise<BackendConfig> {
  const { data } = await api.get(`/backends/${name}/config`)
  return data
}

export async function saveBackendConfig(name: string, config: BackendConfig): Promise<void> {
  await api.put(`/backends/${name}/config`, config)
}

export async function getBackendStats(): Promise<{ stats: BackendStats[] }> {
  const { data } = await api.get('/backends/stats')
  return data
}

// ─── Media Servers ──────────────────────────────────────────────────────────

export async function getMediaServerTypes(): Promise<MediaServerType[]> {
  const { data } = await api.get('/mediaservers/types')
  return data
}

export async function getMediaServerInstances(): Promise<MediaServerInstance[]> {
  const { data } = await api.get('/mediaservers/instances')
  return data
}

export async function saveMediaServerInstances(instances: MediaServerInstance[]): Promise<MediaServerInstance[]> {
  const { data } = await api.put('/mediaservers/instances', instances)
  return data
}

export async function testMediaServer(config: Record<string, unknown>): Promise<MediaServerTestResult> {
  const { data } = await api.post('/mediaservers/test', config)
  return data
}

export async function getMediaServerHealth(): Promise<MediaServerHealthResult[]> {
  const { data } = await api.get('/mediaservers/health')
  return data
}

// ─── Whisper API ──────────────────────────────────────────────────────────
export const getWhisperBackends = () => api.get('/whisper/backends').then(r => r.data)
export const testWhisperBackend = (name: string) => api.post(`/whisper/backends/test/${name}`).then(r => r.data)
export const getWhisperBackendConfig = (name: string) => api.get(`/whisper/backends/config/${name}`).then(r => r.data)
export const saveWhisperBackendConfig = (name: string, config: Record<string, string>) => api.put(`/whisper/backends/config/${name}`, config).then(r => r.data)
export const getWhisperConfig = () => api.get('/whisper/config').then(r => r.data)
export const saveWhisperConfig = (config: Record<string, unknown>) => api.put('/whisper/config', config).then(r => r.data)
export const getWhisperQueue = (params?: { status?: string; limit?: number }) => api.get('/whisper/queue', { params }).then(r => r.data)
export const getWhisperJob = (jobId: string) => api.get(`/whisper/jobs/${jobId}`).then(r => r.data)
export const submitWhisperJob = (data: { file_path: string; language?: string }) => api.post('/whisper/transcribe', data).then(r => r.data)
export const deleteWhisperJob = (jobId: string) => api.delete(`/whisper/jobs/${jobId}`).then(r => r.data)
export const getWhisperStats = () => api.get('/whisper/stats').then(r => r.data)

// ─── Standalone Mode ──────────────────────────────────────────────────────

export async function getWatchedFolders(): Promise<WatchedFolder[]> {
  const { data } = await api.get('/standalone/folders')
  return data
}

export async function saveWatchedFolder(folder: Partial<WatchedFolder> & { path: string }): Promise<WatchedFolder> {
  if (folder.id) {
    const { data } = await api.put(`/standalone/folders/${folder.id}`, folder)
    return data
  }
  const { data } = await api.post('/standalone/folders', folder)
  return data
}

export async function deleteWatchedFolder(folderId: number): Promise<void> {
  await api.delete(`/standalone/folders/${folderId}`)
}

export async function getStandaloneSeries(): Promise<StandaloneSeries[]> {
  const { data } = await api.get('/standalone/series')
  return data
}

export async function getStandaloneMovies(): Promise<StandaloneMovie[]> {
  const { data } = await api.get('/standalone/movies')
  return data
}

export async function triggerStandaloneScan(): Promise<{ message: string }> {
  const { data } = await api.post('/standalone/scan')
  return data
}

export async function getStandaloneStatus(): Promise<StandaloneStatus> {
  const { data } = await api.get('/standalone/status')
  return data
}

export async function refreshSeriesMetadata(seriesId: number): Promise<void> {
  await api.post(`/standalone/series/${seriesId}/refresh-metadata`)
}

export default api
