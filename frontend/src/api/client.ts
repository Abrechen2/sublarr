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
  HookConfig, WebhookConfig,
  StatisticsData, FullBackupInfo, SubtitleToolResult, LogRotationConfig,
  TasksResponse,
  SubtitleContent, SubtitleSaveResult, SubtitleBackup, SubtitleValidation, SubtitleParseResult,
  HealthCheckResult, HealthCheckBatchResult, HealthFixResult, QualityTrend,
  ComparisonResponse, SyncResult, SyncPreviewResult,
  GlobalSearchResults, FilterPreset, FilterScope, BatchAction, BatchActionResult,
  ApiKeyService, BazarrMigrationPreview,
  NotificationTemplate, NotificationHistoryEntry, QuietHoursConfig, TemplateVariable, NotificationFilter,
  DiskSpaceStats, ScanStatus, DuplicateGroup, OrphanedFile, CleanupRule, CleanupHistoryEntry, CleanupPreviewData,
  BazarrMappingReport, CompatBatchResult, ExtendedHealthAllResponse, ExportResult,
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

export async function startWantedBatchSearch(itemIds?: number[], seriesId?: number): Promise<{ status: string; total_items: number }> {
  const body: Record<string, unknown> = {}
  if (itemIds) body.item_ids = itemIds
  if (seriesId) body.series_id = seriesId
  const { data } = await api.post('/wanted/batch-search', body)
  return data
}

/** Start background batch-extract for multiple wanted items or a whole series (returns 202). */
export async function batchExtractEmbedded(
  itemIds: number[],
  autoTranslate = false,
  seriesId?: number,
): Promise<{ status: string; total_items: number }> {
  const body: Record<string, unknown> = { auto_translate: autoTranslate }
  if (seriesId != null) {
    body.series_id = seriesId
  } else {
    body.item_ids = itemIds
  }
  const { data } = await api.post('/wanted/batch-extract', body)
  return data
}

export interface BatchExtractStatus {
  running: boolean
  total: number
  processed: number
  succeeded: number
  failed: number
  current_item: string | null
}

export async function getBatchExtractStatus(): Promise<BatchExtractStatus> {
  const { data } = await api.get('/wanted/batch-extract/status')
  return data
}

/** Start batch search across multiple series at once. */
export async function startSeriesBatchSearch(
  seriesIds: number[],
): Promise<{ queued: number }> {
  const { data } = await api.post('/wanted/batch-search', { series_ids: seriesIds })
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
  const { data } = await api.post(`/providers/test/${name}`, {})
  return {
    provider: data.provider,
    healthy: data.health_check?.healthy ?? false,
    message: data.health_check?.message ?? 'No response',
  }
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

// ─── Interactive Search ───────────────────────────────────────────────────────

export interface InteractiveSearchResult {
  provider_name: string
  subtitle_id: string
  language: string
  format: string
  filename: string
  release_info: string
  score: number
  hearing_impaired: boolean
  forced: boolean
  matches: string[]
  machine_translated?: boolean
  mt_confidence?: number  // 0-100
  uploader_trust_bonus?: number  // 0-20
  uploader_name?: string
}

export interface InteractiveSearchResponse {
  results: InteractiveSearchResult[]
  total: number
  item: { id: number; title: string; item_type: string }
}

export interface DownloadSpecificPayload {
  provider_name: string
  subtitle_id: string
  language: string
  translate: boolean
}

export interface DownloadSpecificResult {
  success: boolean
  path?: string
  format?: string
  translated?: boolean
  error?: string
}

export async function searchInteractive(itemId: number): Promise<InteractiveSearchResponse> {
  const { data } = await api.get(`/wanted/${itemId}/search-providers`)
  return data
}

export async function searchInteractiveEpisode(episodeId: number): Promise<InteractiveSearchResponse> {
  const { data } = await api.get(`/episodes/${episodeId}/search-providers`)
  return data
}

export async function downloadSpecific(itemId: number, payload: DownloadSpecificPayload): Promise<DownloadSpecificResult> {
  const { data } = await api.post(`/wanted/${itemId}/download-specific`, payload)
  return data
}

export async function downloadSpecificEpisode(episodeId: number, payload: DownloadSpecificPayload): Promise<DownloadSpecificResult> {
  const { data } = await api.post(`/episodes/${episodeId}/download-specific`, payload)
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
  series_id: number | null
  source_term: string
  target_term: string
  notes: string
  created_at: string
  updated_at: string
}

export async function getGlossaryEntries(seriesId?: number | null, query?: string): Promise<{ entries: GlossaryEntry[]; series_id: number | null }> {
  const params: Record<string, unknown> = {}
  if (seriesId != null) params.series_id = seriesId
  if (query) params.query = query
  const { data } = await api.get('/glossary', { params })
  return data
}

export async function createGlossaryEntry(entry: { series_id?: number | null; source_term: string; target_term: string; notes?: string }): Promise<GlossaryEntry> {
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

// ─── Events & Hooks ──────────────────────────────────────────────────────

export const getEventCatalog = () => api.get('/events/catalog').then(r => r.data)
export const getHookConfigs = (eventName?: string) => api.get('/hooks', { params: eventName ? { event_name: eventName } : {} }).then(r => r.data)
export const createHookConfig = (data: Partial<HookConfig>) => api.post('/hooks', data).then(r => r.data)
export const updateHookConfig = (id: number, data: Partial<HookConfig>) => api.put(`/hooks/${id}`, data).then(r => r.data)
export const deleteHookConfig = (id: number) => api.delete(`/hooks/${id}`)
export const testHook = (id: number) => api.post(`/hooks/${id}/test`).then(r => r.data)
export const getWebhookConfigs = (eventName?: string) => api.get('/webhooks', { params: eventName ? { event_name: eventName } : {} }).then(r => r.data)
export const createWebhookConfig = (data: Partial<WebhookConfig>) => api.post('/webhooks', data).then(r => r.data)
export const updateWebhookConfig = (id: number, data: Partial<WebhookConfig>) => api.put(`/webhooks/${id}`, data).then(r => r.data)
export const deleteWebhookConfig = (id: number) => api.delete(`/webhooks/${id}`)
export const testWebhook = (id: number) => api.post(`/webhooks/${id}/test`).then(r => r.data)
export const getHookLogs = (params?: { hook_id?: number; webhook_id?: number; limit?: number }) => api.get('/hooks/logs', { params }).then(r => r.data)
export const clearHookLogs = () => api.delete('/hooks/logs')
export const getScoringWeights = () => api.get('/scoring/weights').then(r => r.data)
export const updateScoringWeights = (data: { episode?: Record<string, number>; movie?: Record<string, number> }) => api.put('/scoring/weights', data).then(r => r.data)
export const resetScoringWeights = () => api.delete('/scoring/weights')
export const getProviderModifiers = () => api.get('/scoring/modifiers').then(r => r.data)
export const updateProviderModifiers = (data: Record<string, number>) => api.put('/scoring/modifiers', data).then(r => r.data)
export const deleteProviderModifier = (name: string) => api.delete(`/scoring/modifiers/${name}`)

// ─── Statistics ──────────────────────────────────────────────────────────────

export async function getStatistics(range: string): Promise<StatisticsData> {
  const { data } = await api.get('/statistics', { params: { range } })
  return data
}

export async function exportStatistics(range: string, format: 'json' | 'csv'): Promise<Blob> {
  const { data } = await api.get('/statistics/export', {
    params: { range, format },
    responseType: 'blob',
  })
  return data
}

// ─── Full Backup ─────────────────────────────────────────────────────────────

export async function createFullBackup(): Promise<FullBackupInfo> {
  const { data } = await api.post('/backup/full')
  return data
}

export async function listFullBackups(): Promise<{ backups: FullBackupInfo[] }> {
  const { data } = await api.get('/backup/full/list')
  return data
}

export function downloadFullBackupUrl(filename: string): string {
  return `/api/v1/backup/full/download/${filename}`
}

export async function restoreFullBackup(file: File): Promise<{ status: string; config_imported: string[]; db_restored: boolean }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/backup/full/restore', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ─── Log Rotation ────────────────────────────────────────────────────────────

export async function getLogRotation(): Promise<LogRotationConfig> {
  const { data } = await api.get('/logs/rotation')
  return data
}

export async function updateLogRotation(config: LogRotationConfig): Promise<LogRotationConfig> {
  const { data } = await api.put('/logs/rotation', config)
  return data
}

// ─── Subtitle Tools ──────────────────────────────────────────────────────────

export async function runSubtitleTool(tool: string, params: Record<string, unknown>): Promise<SubtitleToolResult> {
  const { data } = await api.post(`/tools/${tool}`, params)
  return data
}

export async function previewSubtitle(filePath: string): Promise<{ format: string; lines: string[]; total_lines: number }> {
  const { data } = await api.get('/tools/preview', { params: { file_path: filePath } })
  return data
}

export async function getSubtitleContent(filePath: string): Promise<SubtitleContent> {
  const { data } = await api.get('/tools/content', { params: { file_path: filePath } })
  return data
}

export async function saveSubtitleContent(filePath: string, content: string, lastModified: number): Promise<SubtitleSaveResult> {
  const { data } = await api.put('/tools/content', { file_path: filePath, content, last_modified: lastModified })
  return data
}

export async function getSubtitleBackup(filePath: string): Promise<SubtitleBackup> {
  const { data } = await api.get('/tools/backup', { params: { file_path: filePath } })
  return data
}

export async function validateSubtitle(content: string, format?: string, filePath?: string): Promise<SubtitleValidation> {
  const { data } = await api.post('/tools/validate', { content, format, file_path: filePath })
  return data
}

export async function parseSubtitleCues(filePath: string): Promise<SubtitleParseResult> {
  const { data } = await api.post('/tools/parse', { file_path: filePath })
  return data
}

// ─── Scheduler Tasks ────────────────────────────────────────────────────────

export async function getTasks(): Promise<TasksResponse> {
  const { data } = await api.get('/tasks')
  return data
}

// ─── Health Check & Sync ────────────────────────────────────────────────────

export async function runHealthCheck(filePath: string): Promise<HealthCheckResult> {
  const { data } = await api.post('/tools/health-check', { file_path: filePath })
  return data
}

export async function runHealthCheckBatch(filePaths: string[]): Promise<HealthCheckBatchResult> {
  const { data } = await api.post('/tools/health-check', { file_paths: filePaths })
  return data
}

export async function applyHealthFix(filePath: string, fixes: string[]): Promise<HealthFixResult> {
  const { data } = await api.post('/tools/health-fix', { file_path: filePath, fixes })
  return data
}

export async function getQualityTrends(days?: number): Promise<{ trends: QualityTrend[]; days: number }> {
  const { data } = await api.get('/tools/quality-trends', { params: { days } })
  return data
}

export async function compareSubtitles(filePaths: string[]): Promise<ComparisonResponse> {
  const { data } = await api.post('/tools/compare', { file_paths: filePaths })
  return data
}

export async function advancedSync(
  filePath: string,
  operation: 'offset' | 'speed' | 'framerate',
  params: Record<string, number>,
  preview?: boolean
): Promise<SyncResult | SyncPreviewResult> {
  const { data } = await api.post('/tools/advanced-sync', {
    file_path: filePath,
    operation,
    ...params,
    preview: preview ?? false,
  })
  return data
}


// ─── Phase 22: Auto-Sync ─────────────────────────────────────────────────────

export async function autoSyncFile(
  filePath: string,
  mediaPath?: string,
  engine?: string,
): Promise<import('@/lib/types').AutoSyncResult> {
  const body: Record<string, unknown> = { file_path: filePath }
  if (mediaPath) body.media_path = mediaPath
  if (engine) body.engine = engine
  const { data } = await api.post('/tools/auto-sync', body)
  return data
}

export async function autoSyncBulk(
  scope: 'series' | 'library',
  seriesId?: number,
  engine?: string,
): Promise<import('@/lib/types').AutoSyncBulkResult> {
  const body: Record<string, unknown> = { scope }
  if (seriesId !== undefined) body.series_id = seriesId
  if (engine) body.engine = engine
  const { data } = await api.post('/tools/auto-sync/bulk', body)
  return data
}

// ─── Phase 12: Search + Filter Presets + Batch Actions ────────────────────

export async function searchGlobal(q: string, limit = 20): Promise<GlobalSearchResults> {
  const res = await api.get('/search', { params: { q, limit } })
  return res.data
}

export async function getFilterPresets(scope: FilterScope): Promise<FilterPreset[]> {
  const res = await api.get('/filter-presets', { params: { scope } })
  return res.data
}

export async function createFilterPreset(preset: Omit<FilterPreset, 'id' | 'created_at' | 'updated_at'>): Promise<FilterPreset> {
  const res = await api.post('/filter-presets', preset)
  return res.data
}

export async function updateFilterPreset(id: number, data: Partial<Pick<FilterPreset, 'name' | 'conditions' | 'is_default'>>): Promise<FilterPreset> {
  const res = await api.put(`/filter-presets/${id}`, data)
  return res.data
}

export async function deleteFilterPreset(id: number): Promise<void> {
  await api.delete(`/filter-presets/${id}`)
}

export async function batchAction(itemIds: number[], action: BatchAction): Promise<BatchActionResult> {
  const res = await api.post('/wanted/batch-action', { item_ids: itemIds, action })
  return res.data
}

// ─── API Key Management ──────────────────────────────────────────────────────

export async function getApiKeys(): Promise<{ services: ApiKeyService[] }> {
  const { data } = await api.get('/api-keys')
  return data
}

export async function getApiKeyService(service: string): Promise<ApiKeyService> {
  const { data } = await api.get(`/api-keys/${service}`)
  return data
}

export async function updateApiKey(service: string, keyName: string, value: string): Promise<{ status: string }> {
  const { data } = await api.put(`/api-keys/${service}`, { key_name: keyName, value })
  return data
}

export async function testApiKey(service: string): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post(`/api-keys/${service}/test`)
  return data
}

export async function exportApiKeys(): Promise<Blob> {
  const { data } = await api.post('/api-keys/export', {}, { responseType: 'blob' })
  return data
}

export async function importApiKeys(file: File): Promise<{ status: string; imported: number; skipped: number }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api-keys/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function importBazarrConfig(file: File): Promise<BazarrMigrationPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api-keys/import/bazarr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function confirmBazarrImport(preview: BazarrMigrationPreview): Promise<{ status: string; imported: number }> {
  const { data } = await api.post('/api-keys/import/bazarr/confirm', preview)
  return data
}

// ─── Notification Templates ──────────────────────────────────────────────────

export async function getNotificationTemplates(): Promise<{ templates: NotificationTemplate[] }> {
  const { data } = await api.get('/notifications/templates')
  return data
}

export async function createNotificationTemplate(template: Partial<NotificationTemplate>): Promise<NotificationTemplate> {
  const { data } = await api.post('/notifications/templates', template)
  return data
}

export async function updateNotificationTemplate(id: number, template: Partial<NotificationTemplate>): Promise<NotificationTemplate> {
  const { data } = await api.put(`/notifications/templates/${id}`, template)
  return data
}

export async function deleteNotificationTemplate(id: number): Promise<void> {
  await api.delete(`/notifications/templates/${id}`)
}

export async function previewNotificationTemplate(id: number): Promise<{ title: string; body: string }> {
  const { data } = await api.post(`/notifications/templates/${id}/preview`)
  return data
}

export async function getTemplateVariables(eventType?: string): Promise<{ variables: TemplateVariable[] }> {
  const params = eventType ? { event_type: eventType } : {}
  const { data } = await api.get('/notifications/variables', { params })
  return data
}

export async function getQuietHours(): Promise<{ configs: QuietHoursConfig[] }> {
  const { data } = await api.get('/notifications/quiet-hours')
  return data
}

export async function createQuietHours(config: Partial<QuietHoursConfig>): Promise<QuietHoursConfig> {
  const { data } = await api.post('/notifications/quiet-hours', config)
  return data
}

export async function updateQuietHours(id: number, config: Partial<QuietHoursConfig>): Promise<QuietHoursConfig> {
  const { data } = await api.put(`/notifications/quiet-hours/${id}`, config)
  return data
}

export async function deleteQuietHours(id: number): Promise<void> {
  await api.delete(`/notifications/quiet-hours/${id}`)
}

export async function getNotificationHistory(page = 1, eventType?: string): Promise<{
  entries: NotificationHistoryEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}> {
  const params: Record<string, unknown> = { page, per_page: 25 }
  if (eventType) params.event_type = eventType
  const { data } = await api.get('/notifications/history', { params })
  return data
}

export async function resendNotification(id: number): Promise<{ status: string }> {
  const { data } = await api.post(`/notifications/history/${id}/resend`)
  return data
}

export async function getNotificationFilters(): Promise<NotificationFilter> {
  const { data } = await api.get('/notifications/filters')
  return data
}

export async function updateNotificationFilters(filters: NotificationFilter): Promise<NotificationFilter> {
  const { data } = await api.put('/notifications/filters', filters)
  return data
}

// ─── Cleanup System ─────────────────────────────────────────────────────────

export async function getCleanupStats(): Promise<DiskSpaceStats> {
  const { data } = await api.get('/cleanup/stats')
  return data
}

export async function startCleanupScan(): Promise<{ scan_id: string; message: string }> {
  const { data } = await api.post('/cleanup/scan')
  return data
}

export async function getCleanupScanStatus(): Promise<ScanStatus> {
  const { data } = await api.get('/cleanup/scan/status')
  return data
}

export async function getDuplicates(page = 1, perPage = 50): Promise<{ groups: DuplicateGroup[]; total: number; page: number }> {
  const { data } = await api.get('/cleanup/duplicates', { params: { page, per_page: perPage } })
  return data
}

export async function deleteDuplicates(selections: { keep: string; delete: string[] }[]): Promise<{ deleted: number; bytes_freed: number }> {
  const { data } = await api.post('/cleanup/duplicates/delete', { selections })
  return data
}

export async function scanOrphaned(): Promise<{ message: string }> {
  const { data } = await api.post('/cleanup/orphaned/scan')
  return data
}

export async function getOrphanedFiles(): Promise<{ files: OrphanedFile[]; total: number }> {
  const { data } = await api.get('/cleanup/orphaned')
  return data
}

export async function deleteOrphaned(filePaths: string[]): Promise<{ deleted: number; bytes_freed: number }> {
  const { data } = await api.post('/cleanup/orphaned/delete', { file_paths: filePaths })
  return data
}

export async function getCleanupRules(): Promise<CleanupRule[]> {
  const { data } = await api.get('/cleanup/rules')
  return data
}

export async function createCleanupRule(rule: Omit<CleanupRule, 'id' | 'last_run_at' | 'created_at'>): Promise<CleanupRule> {
  const { data } = await api.post('/cleanup/rules', rule)
  return data
}

export async function updateCleanupRule(id: number, rule: Partial<CleanupRule>): Promise<CleanupRule> {
  const { data } = await api.put(`/cleanup/rules/${id}`, rule)
  return data
}

export async function deleteCleanupRule(id: number): Promise<void> {
  await api.delete(`/cleanup/rules/${id}`)
}

// ─── Audio ──────────────────────────────────────────────────────────────────

export interface WaveformData {
  duration: number
  sample_rate: number
  samples: number
  data: Array<{ time: number; amplitude: number }>
}

export async function getWaveform(
  filePath: string,
  audioTrackIndex?: number,
  width = 2000,
  sampleRate = 100,
): Promise<WaveformData> {
  const params: Record<string, unknown> = { file_path: filePath, width, sample_rate: sampleRate }
  if (audioTrackIndex !== undefined) params.audio_track_index = audioTrackIndex
  const { data } = await api.get('/audio/waveform', { params })
  return data
}

export async function extractAudio(filePath: string, audioTrackIndex?: number): Promise<{ audio_path: string; duration: number }> {
  const { data } = await api.post('/audio/extract', { file_path: filePath, audio_track_index: audioTrackIndex })
  return data
}

// ─── Spell Checking ───────────────────────────────────────────────────────────

export interface SpellCheckError {
  word: string
  position: number
  suggestions: string[]
  line?: number
  text?: string
  start_time?: number
  end_time?: number
}

export interface SpellCheckResult {
  errors: SpellCheckError[]
  total_words: number
  error_count: number
  error?: string
}

export async function checkSpelling(
  filePath?: string,
  content?: string,
  language = 'en_US',
  customWords?: string[],
): Promise<SpellCheckResult> {
  const { data } = await api.post('/spell/check', {
    file_path: filePath,
    content,
    language,
    custom_words: customWords,
  })
  return data
}

export async function getSpellDictionaries(): Promise<{ dictionaries: string[] }> {
  const { data } = await api.get('/spell/dictionaries')
  return data
}

// ─── OCR ───────────────────────────────────────────────────────────────────────

export interface OCRExtractResult {
  text: string
  frames: number
  successful_frames: number
  quality: number
}

export interface OCRPreviewResult {
  frame_path: string
  preview_text: string
}

export async function extractOCR(
  filePath: string,
  streamIndex: number,
  language = 'eng',
  startTime?: number,
  endTime?: number,
  interval = 1.0,
): Promise<OCRExtractResult> {
  const { data } = await api.post('/ocr/extract', {
    file_path: filePath,
    stream_index: streamIndex,
    language,
    start_time: startTime,
    end_time: endTime,
    interval,
  })
  return data
}

export async function previewOCRFrame(
  filePath: string,
  timestamp: number,
  streamIndex?: number,
): Promise<OCRPreviewResult> {
  const params: Record<string, unknown> = { file_path: filePath, timestamp }
  if (streamIndex !== undefined) params.stream_index = streamIndex
  const { data } = await api.get('/ocr/preview', { params })
  return data
}

export async function runCleanupRule(id: number): Promise<{ message: string }> {
  const { data } = await api.post(`/cleanup/rules/${id}/run`)
  return data
}

export async function getCleanupHistory(page = 1, perPage = 50): Promise<{ entries: CleanupHistoryEntry[]; total: number; page: number }> {
  const { data } = await api.get('/cleanup/history', { params: { page, per_page: perPage } })
  return data
}

export async function getCleanupPreview(ruleId?: number): Promise<CleanupPreviewData> {
  const { data } = await api.post('/cleanup/preview', { rule_id: ruleId })
  return data
}

// ─── External Integrations ──────────────────────────────────────────────────

export async function getBazarrMappingReport(dbPath: string): Promise<BazarrMappingReport> {
  const { data } = await api.post('/integrations/bazarr/mapping-report', { db_path: dbPath })
  return data
}

export async function runCompatCheck(
  subtitlePaths: string[],
  videoPath: string,
  target: string,
): Promise<CompatBatchResult> {
  const { data } = await api.post('/integrations/compat-check', {
    subtitle_paths: subtitlePaths,
    video_path: videoPath,
    target,
  })
  return data
}

export async function runSingleCompatCheck(
  subtitlePath: string,
  videoPath: string,
  target: string,
): Promise<CompatBatchResult> {
  const { data } = await api.post('/integrations/compat-check/single', {
    subtitle_path: subtitlePath,
    video_path: videoPath,
    target,
  })
  return data
}

export async function getExtendedHealthAll(): Promise<ExtendedHealthAllResponse> {
  const { data } = await api.get('/integrations/health/all')
  return data
}

export async function exportIntegrationConfig(
  format: string,
  includeSecrets: boolean,
): Promise<ExportResult> {
  const { data } = await api.post('/integrations/export', {
    format,
    include_secrets: includeSecrets,
  })
  return data
}

export async function exportIntegrationConfigZip(
  formats: string[],
  includeSecrets: boolean,
): Promise<Blob> {
  const { data } = await api.post('/integrations/export/zip', {
    formats,
    include_secrets: includeSecrets,
  }, { responseType: 'blob' })
  return data
}

// ─── Marketplace ────────────────────────────────────────────────────────────────

export interface MarketplacePlugin {
  name: string
  version: string
  description: string
  author: string
  category: 'provider' | 'translation' | 'tool'
  url: string
  rating?: number
  downloads?: number
}

export interface MarketplacePluginInfo extends MarketplacePlugin {
  readme?: string
  changelog?: string
  dependencies?: string[]
  requirements?: string[]
}

export interface PluginInstallResult {
  status: 'installed' | 'failed'
  path?: string
  validation?: {
    valid: boolean
    errors: string[]
    warnings: string[]
  }
  error?: string
}

export async function getMarketplacePlugins(category?: string): Promise<{ plugins: MarketplacePlugin[] }> {
  const params: Record<string, unknown> = {}
  if (category) params.category = category
  const { data } = await api.get('/marketplace/plugins', { params })
  return data
}

export async function getMarketplacePlugin(pluginName: string): Promise<MarketplacePluginInfo> {
  const { data } = await api.get(`/marketplace/plugins/${pluginName}`)
  return data
}

export async function installMarketplacePlugin(
  pluginName: string,
  version?: string,
): Promise<PluginInstallResult> {
  const { data } = await api.post('/marketplace/install', { plugin_name: pluginName, version })
  return data
}

export async function uninstallMarketplacePlugin(pluginName: string): Promise<{ message: string }> {
  const { data } = await api.post('/marketplace/uninstall', { plugin_name: pluginName })
  return data
}

export async function checkMarketplaceUpdates(
  installedPlugins: string[],
): Promise<Record<string, { available: boolean; latest_version?: string }>> {
  const { data } = await api.get('/marketplace/updates', { params: { installed: installedPlugins } })
  return data.updates || {}
}

// --- Phase 28-01: LLM Backend Presets ---

export interface BackendTemplate {
  name: string
  display_name: string
  backend_type: string
  description: string
  config_defaults: Record<string, unknown>
}

export async function getBackendTemplates(): Promise<{ templates: BackendTemplate[] }> {
  const response = await api.get('/backends/templates')
  return response.data
}

// --- Phase 20-02: Translation Memory ---

export interface TranslationMemoryStats {
  entries: number
  cache_size_bytes?: number
}

export async function getTranslationMemoryStats(): Promise<TranslationMemoryStats> {
  const { data } = await api.get('/translation-memory/stats')
  return data
}

export async function clearTranslationMemoryCache(): Promise<{ cleared: boolean; deleted: number }> {
  const { data } = await api.delete('/translation-memory/cache')
  return data
}

// --- Phase 25-02: AniDB Absolute Episode Order ---

export async function updateSeriesSettings(
  seriesId: number,
  settings: { absolute_order: boolean }
): Promise<{ success: boolean }> {
  const response = await api.put(`/library/series/${seriesId}/settings`, settings)
  return response.data
}

export async function getAnidbMappingStatus(): Promise<{
  last_sync?: string
  entry_count?: number
  status: string
}> {
  const response = await api.get('/anidb-mapping/status')
  return response.data
}

export async function refreshAnidbMapping(): Promise<{ success: boolean; message?: string }> {
  const response = await api.post('/anidb-mapping/refresh')
  return response.data
}

// ─── Phase 30/31: Video Sync ──────────────────────────────────────────────────

export async function getSyncEngines(): Promise<Record<string, boolean>> {
  const { data } = await api.get('/tools/video-sync/engines')
  return data
}

export async function installSyncEngine(engine: 'ffsubsync' | 'alass'): Promise<{ success: boolean; message?: string; error?: string }> {
  const { data } = await api.post(`/tools/video-sync/install/${engine}`)
  return data
}

export async function startVideoSync(params: {
  file_path: string
  video_path: string
  engine: 'ffsubsync' | 'alass'
  reference_track_index?: number
}): Promise<{ job_id: string }> {
  const { data } = await api.post('/tools/video-sync', params)
  return data
}

export async function getSyncJobStatus(jobId: string): Promise<{
  status: string
  result?: Record<string, unknown>
  error?: string
}> {
  const { data } = await api.get(`/tools/video-sync/${jobId}`)
  return data
}

// ─── Phase 35: Quality fixes ───────────────────────────────────────────────────

export async function overlapFix(filePath: string): Promise<{ fixed: number; backup_path: string }> {
  const { data } = await api.post('/tools/overlap-fix', { file_path: filePath })
  return data as { fixed: number; backup_path: string }
}

export async function timingNormalize(filePath: string, minMs = 500, maxMs = 10000): Promise<{ extended: number; too_long: number; backup_path: string }> {
  const { data } = await api.post('/tools/timing-normalize', { file_path: filePath, min_ms: minMs, max_ms: maxMs })
  return data as { extended: number; too_long: number; backup_path: string }
}

export async function mergeLines(filePath: string, gapMs = 200): Promise<{ merged: number; backup_path: string }> {
  const { data } = await api.post('/tools/merge-lines', { file_path: filePath, gap_ms: gapMs })
  return data as { merged: number; backup_path: string }
}

export async function splitLines(filePath: string, maxChars = 80): Promise<{ split: number; backup_path: string }> {
  const { data } = await api.post('/tools/split-lines', { file_path: filePath, max_chars: maxChars })
  return data as { split: number; backup_path: string }
}

export async function spellCheck(filePath: string, language = 'de_DE'): Promise<{ errors: { word: string; start_ms: number; text: string }[]; total: number }> {
  const { data } = await api.post('/tools/spell-check', { file_path: filePath, language })
  return data as { errors: { word: string; start_ms: number; text: string }[]; total: number }
}

// ─── Phase 33: Format conversion ──────────────────────────────────────────────

export async function convertSubtitle(params: {
  file_path?: string
  track_index?: number
  video_path?: string
  target_format: 'srt' | 'ass' | 'ssa' | 'vtt'
}): Promise<{ output_path: string; format: string }> {
  const { data } = await api.post('/tools/convert', params)
  return data as { output_path: string; format: string }
}

// ─── Phase 32: Waveform extraction ────────────────────────────────────────────

export async function extractWaveform(videoPath: string): Promise<{ audio_url: string; duration_s: number }> {
  const { data } = await api.post('/tools/waveform-extract', { video_path: videoPath })
  return data as { audio_url: string; duration_s: number }
}

// ─── Phase 29: Track Manifest ─────────────────────────────────────────────────

export async function listEpisodeTracks(epId: number): Promise<import('@/lib/types').EpisodeTracksResponse> {
  const { data } = await api.get(`/library/episodes/${epId}/tracks`)
  return data
}

export async function extractTrack(epId: number, index: number, language?: string): Promise<import('@/lib/types').ExtractTrackResult> {
  const body: Record<string, unknown> = {}
  if (language) body.language = language
  const { data } = await api.post(`/library/episodes/${epId}/tracks/${index}/extract`, body)
  return data
}

export async function trackAsSource(epId: number, index: number): Promise<import('@/lib/types').TrackAsSourceResult> {
  const { data } = await api.post(`/library/episodes/${epId}/tracks/${index}/use-as-source`)
  return data
}

export default api
