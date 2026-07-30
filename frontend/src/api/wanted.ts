import { api } from './core'
import type { PaginatedJobs, Job, PaginatedWanted, WantedSummary, WantedSearchResponse, WantedBatchStatus, BatchState } from '@/lib/types'

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

export async function retryJob(jobId: string): Promise<{ status: string; job_id: string }> {
  const { data } = await api.post(`/jobs/${jobId}/retry`)
  return data
}

/** Cancel a queued job (soft-cancel) or delete a finished one from history.
 *  Named cancelQueuedJob (not cancelJob) — api/translation.ts already exports
 *  a cancelJob for the live-queue cooperative cancel, and both modules are
 *  re-exported star-style through api/client.ts. */
export async function cancelQueuedJob(jobId: string): Promise<{ status: string; job_id: string }> {
  const { data } = await api.delete(`/jobs/${jobId}`)
  return data
}

/** Cancel all queued translation jobs. Returns the number cancelled. */
export async function clearQueuedJobs(): Promise<{ cancelled: number }> {
  const { data } = await api.post('/jobs/clear-queued')
  return data
}

// ─── Wanted ─────────────────────────────────────────────────────────────

export async function getWantedItems(
  page = 1, perPage = 50, itemType?: string, status?: string,
  subtitleType?: string, movieId?: number, sonarrSeriesId?: number,
  search?: string, sortBy?: string, sortDir?: string
): Promise<PaginatedWanted> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (itemType) params.item_type = itemType
  if (status) params.status = status
  if (subtitleType) params.subtitle_type = subtitleType
  if (movieId != null) params.movie_id = movieId
  if (sonarrSeriesId != null) params.series_id = sonarrSeriesId
  if (search) params.search = search
  if (sortBy) params.sort_by = sortBy
  if (sortDir) params.sort_dir = sortDir
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

/** Queue multiple wanted items for re-translation. */
export async function batchTranslate(
  itemIds: number[],
): Promise<{ queued: number; job_ids: string[] }> {
  const { data } = await api.post('/wanted/batch-translate', { item_ids: itemIds })
  return data
}

export interface BatchExtractStatus {
  running: boolean
  total: number
  processed: number
  succeeded: number
  failed: number
  skipped: number
  current_item: string | null
}

export async function getBatchExtractStatus(): Promise<BatchExtractStatus> {
  const { data } = await api.get('/wanted/batch-extract/status')
  return data
}

export interface CleanupSidecarsResult {
  deleted: string[]
  kept: string[]
  errors: string[]
  dry_run: boolean
}

export async function cleanupSidecars(
  itemIds?: number[],
  dryRun = false,
): Promise<CleanupSidecarsResult> {
  const body: Record<string, unknown> = { dry_run: dryRun }
  if (itemIds?.length) body.item_ids = itemIds
  const { data } = await api.post('/wanted/cleanup', body)
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

/** One item's dry-run (pipeline preview) outcome — nothing was written. */
export interface WantedDryRunResult {
  wanted_id: number
  status: 'found' | 'not_found' | 'skipped' | 'failed' | 'error'
  dry_run?: boolean
  provider?: string
  score?: number
  format?: string
  output_path?: string
  reason?: string
  error?: string
}

/** Preview what the automation pipeline would download, without writing anything. */
export async function dryRunWanted(itemIds: number[]): Promise<{ results: WantedDryRunResult[] }> {
  const { data } = await api.post('/wanted/dry-run', { item_ids: itemIds }, { timeout: 300_000 })
  return data
}

export interface BatchProbeStatus {
  running: boolean
  total: number
  processed: number
  extracted: number
  found: number
  skipped: number
  failed: number
  current_item: string | null
}

export async function getBatchProbeStatus(): Promise<BatchProbeStatus> {
  const { data } = await api.get('/wanted/batch-probe/status')
  return data
}

export async function startBatchProbe(seriesId?: number): Promise<{ status: string; total_items: number }> {
  const body: Record<string, unknown> = {}
  if (seriesId != null) body.series_id = seriesId
  const { data } = await api.post('/wanted/batch-probe', body)
  return data
}

export interface ScannerStatus {
  is_scanning: boolean
  is_searching: boolean
  progress: { current: number; total: number; phase: string; added: number; updated: number }
  last_scan_at: string | null
  last_search_at: string | null
  last_summary: Record<string, unknown> | null
}

export async function getScannerStatus(): Promise<ScannerStatus> {
  const { data } = await api.get('/wanted/scanner/status')
  return data
}

// ─── Subtitle Automation (0.71.0) ───────────────────────────────────────────

export interface AutomationQueueCounts {
  pending: number
  running: number
  failed: number
  done: number
}

export interface AutomationStatus {
  enabled: boolean
  queue_size: number
  queue: AutomationQueueCounts
  last_run_at: string | null
  last_run_status: string | null
  last_error: string | null
}

export async function getAutomationStatus(): Promise<AutomationStatus> {
  const { data } = await api.get('/wanted/automation/status')
  return data
}

export async function runAutomationNow(): Promise<{ status: string; processed?: number }> {
  const { data } = await api.post('/wanted/automation/run-now')
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

// ─── Phase 12: Search + Filter Presets + Batch Actions ────────────────────

export async function searchGlobal(q: string, limit = 20): Promise<import('@/lib/types').GlobalSearchResults> {
  const res = await api.get('/search', { params: { q, limit } })
  return res.data
}

export async function getFilterPresets(scope: import('@/lib/types').FilterScope): Promise<import('@/lib/types').FilterPreset[]> {
  const res = await api.get('/filter-presets', { params: { scope } })
  return res.data
}

export async function createFilterPreset(preset: Omit<import('@/lib/types').FilterPreset, 'id' | 'created_at' | 'updated_at'>): Promise<import('@/lib/types').FilterPreset> {
  const res = await api.post('/filter-presets', preset)
  return res.data
}

export async function updateFilterPreset(id: number, data: Partial<Pick<import('@/lib/types').FilterPreset, 'name' | 'conditions' | 'is_default'>>): Promise<import('@/lib/types').FilterPreset> {
  const res = await api.put(`/filter-presets/${id}`, data)
  return res.data
}

export async function deleteFilterPreset(id: number): Promise<void> {
  await api.delete(`/filter-presets/${id}`)
}

export async function batchAction(itemIds: number[], action: import('@/lib/types').BatchAction): Promise<import('@/lib/types').BatchActionResult> {
  const res = await api.post('/wanted/batch-action', { item_ids: itemIds, action })
  return res.data
}

// ─── Provisional-MT pending-original review (feature #8b Phase 2, Task 3/4) ──
// Backend: routes/wanted/mt_pending.py. A `mt_on_original_found="notify"`
// re-seek pass records a candidate original on the wanted row without
// touching any files; these endpoints list it and let the user approve
// (install the original, trash the MT) or reject (keep the MT, pin it).

export interface MtPendingOriginal {
  provider: string
  score: number
  output_path: string
  format: string
  found_at: string
}

export interface MtPendingItem {
  id: number
  title: string
  season_episode: string
  file_path: string
  item_type: 'episode' | 'movie'
  mt_pending_original: MtPendingOriginal
}

export interface MtPendingListResponse {
  data: MtPendingItem[]
  total: number
}

export async function getMtPendingItems(): Promise<MtPendingListResponse> {
  const { data } = await api.get('/wanted/mt-pending')
  return data
}

export async function approveMtPending(itemId: number): Promise<{ status: string; id: number }> {
  const { data } = await api.post(`/wanted/${itemId}/mt-pending/approve`)
  return data
}

export async function rejectMtPending(itemId: number): Promise<{ status: string; id: number }> {
  const { data } = await api.post(`/wanted/${itemId}/mt-pending/reject`)
  return data
}

// ─── Export ─────────────────────────────────────────────────────────────

/** Downloads the wanted list (with the given filters applied) as CSV or JSON. */
export async function exportWantedItems(opts: {
  format: 'csv' | 'json'
  itemType?: string
  status?: string
  subtitleType?: string
  search?: string
}): Promise<void> {
  const params: Record<string, unknown> = { format: opts.format }
  if (opts.itemType) params.item_type = opts.itemType
  if (opts.status) params.status = opts.status
  if (opts.subtitleType) params.subtitle_type = opts.subtitleType
  if (opts.search) params.search = opts.search
  const { data, headers } = await api.get('/wanted/export', {
    params,
    responseType: 'blob',
  })
  const disposition: string = headers['content-disposition'] ?? ''
  const match = disposition.match(/filename[^;=\n]*=["']?([^"';\n]+)["']?/)
  const filename = match ? match[1].trim() : `sublarr-wanted.${opts.format}`
  const url = URL.createObjectURL(data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
