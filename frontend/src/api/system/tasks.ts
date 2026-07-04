import { api } from '../core'
import type {
  TasksResponse,
  HealthCheckResult, HealthCheckBatchResult, HealthFixResult, QualityTrend,
  ComparisonResponse, SyncResult, SyncPreviewResult,
  ChapterList,
  DiskSpaceStats, ScanStatus, DuplicateGroup, OrphanedFile, CleanupRule, CleanupHistoryEntry, CleanupPreviewData,
} from '@/lib/types'

// ─── Scheduler Tasks ─────────────────────────────────────────────────────────

export async function getTasks(): Promise<TasksResponse> {
  const { data } = await api.get('/tasks')
  return data
}

// ─── Health Check & Sync ─────────────────────────────────────────────────────

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
  preview?: boolean,
  chapterRange?: { start_ms: number; end_ms: number }
): Promise<SyncResult | SyncPreviewResult> {
  const { data } = await api.post('/tools/advanced-sync', {
    file_path: filePath,
    operation,
    ...params,
    preview: preview ?? false,
    ...(chapterRange ? { chapter_range: chapterRange } : {}),
  })
  return data
}

// ─── Video Sync ───────────────────────────────────────────────────────────────

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

export interface SyncCue {
  start: number
  end: number
  text: string
}

export interface SyncCandidate {
  engine: 'ffsubsync' | 'alass'
  status: 'ok' | 'unavailable' | 'rejected' | 'error'
  shift_ms?: number
  cues?: SyncCue[]
  error?: string
}

export interface SyncCompareResult {
  original: SyncCue[]
  candidates: SyncCandidate[]
  any_output: boolean
}

export async function syncCompare(params: {
  file_path: string
  video_path?: string
  reference_path?: string
}): Promise<SyncCompareResult> {
  const { data } = await api.post('/tools/video-sync/compare', params)
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

export async function getVideoChapters(videoPath: string): Promise<ChapterList> {
  const { data } = await api.get('/tools/chapters', {
    params: { video_path: videoPath },
  })
  return data
}

// ─── Auto-Sync ───────────────────────────────────────────────────────────────

export async function autoSyncFile(
  filePath: string,
  videoPath?: string,
  engine?: string,
): Promise<import('@/lib/types').AutoSyncResult> {
  const body: Record<string, unknown> = { file_path: filePath }
  if (videoPath) body.video_path = videoPath
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

// ─── Cleanup System ───────────────────────────────────────────────────────────

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
  // Backend returns { running: bool, scan_id, result }
  // Normalize to ScanStatus shape: { status: 'idle'|'scanning', ... }
  return {
    status: data.running ? 'scanning' : 'idle',
    progress: data.progress ?? 0,
    total: data.total ?? 0,
    scan_id: data.scan_id ?? null,
    ...data,
  }
}

export async function getDuplicates(page = 1, perPage = 50): Promise<{ groups: DuplicateGroup[]; total: number; page: number }> {
  const { data } = await api.get('/cleanup/duplicates', { params: { page, per_page: perPage } })
  return data
}

export async function deleteDuplicates(selections: { keep: string; delete: string[] }[]): Promise<{ deleted: number; bytes_freed: number }> {
  const { data } = await api.post('/cleanup/duplicates/delete', { groups: selections })
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
  return Array.isArray(data) ? data : (data.rules ?? [])
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

export async function runCleanupRule(id: number): Promise<{ message: string }> {
  const { data } = await api.post(`/cleanup/rules/${id}/run`)
  return data
}

export async function previewCleanupRule(id: number): Promise<{
  rule_id: number
  rule_type: string
  preview: Record<string, number>
}> {
  const { data } = await api.post(`/cleanup/rules/${id}/preview`)
  return data
}

export async function getCleanupHistory(page = 1, perPage = 50): Promise<{ entries: CleanupHistoryEntry[]; total: number; page: number }> {
  const { data } = await api.get('/cleanup/history', { params: { page, per_page: perPage } })
  // Backend returns { items, total, page, per_page } — normalize to { entries }
  return { ...data, entries: data.entries ?? data.items ?? [] }
}

export async function getCleanupPreview(_ruleId?: number): Promise<CleanupPreviewData> {
  // Backend expects { action: "dedup"|"orphaned"|"rule" }
  const { data } = await api.post('/cleanup/preview', { action: 'dedup' })
  // Backend returns { affected_files: [{path, size, ...}], total_size, ... }
  // Normalize to CleanupPreviewData shape
  const files = (data.affected_files ?? []).map((f: { path: string; size?: number; size_bytes?: number }) => ({
    path: f.path,
    size_bytes: f.size_bytes ?? f.size ?? 0,
    action: 'delete',
  }))
  return {
    files,
    total_size_bytes: data.total_size ?? 0,
    total_files: files.length,
  }
}
