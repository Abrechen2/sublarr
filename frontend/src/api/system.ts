import { api } from './core'
import type {
  PaginatedBlacklist, PaginatedHistory, HistoryStats,
  WatchedFolder, StandaloneSeries, StandaloneMovie, StandaloneStatus,
  StatisticsData, FullBackupInfo, SubtitleToolResult, LogRotationConfig,
  TasksResponse,
  SubtitleContent, SubtitleSaveResult, SubtitleBackup, SubtitleValidation, SubtitleParseResult,
  HealthCheckResult, HealthCheckBatchResult, HealthFixResult, QualityTrend,
  ComparisonResponse, SyncResult, SyncPreviewResult,
  BazarrMappingReport, CompatBatchResult, ExtendedHealthAllResponse, ExportResult,
  ChapterList,
  SubtitleDiffResult,
  SupportPreview,
  DiskSpaceStats, ScanStatus, DuplicateGroup, OrphanedFile, CleanupRule, CleanupHistoryEntry, CleanupPreviewData,
  NotificationTemplate, NotificationHistoryEntry, QuietHoursConfig, TemplateVariable, NotificationFilter,
} from '@/lib/types'

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

export async function rescanSeries(seriesId: number): Promise<{ message: string; series_id: number }> {
  const { data } = await api.post(`/standalone/series/${seriesId}/scan`)
  return data
}

export async function refreshSeriesMetadata(seriesId: number): Promise<void> {
  await api.post(`/standalone/series/${seriesId}/refresh-metadata`)
}

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

// ─── Support Export ───────────────────────────────────────────────────────────

export async function fetchSupportPreview(): Promise<SupportPreview> {
  const res = await api.get<SupportPreview>('/logs/support-preview')
  return res.data
}

export async function downloadSupportBundle(): Promise<void> {
  const res = await api.get('/logs/support-export', { responseType: 'blob' })
  const contentDisposition = res.headers['content-disposition'] as string | undefined
  const filenameMatch = contentDisposition?.match(/filename="?([^"]+)"?/)
  const filename =
    filenameMatch?.[1] ??
    `sublarr-support-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
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

// ─── Phase 22: Auto-Sync ─────────────────────────────────────────────────────

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

export async function getVideoChapters(videoPath: string): Promise<ChapterList> {
  const { data } = await api.get('/tools/chapters', {
    params: { video_path: videoPath },
  })
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

export async function removeCredits(
  filePath: string,
  dryRun = false
): Promise<{
  status: string
  original_lines: number
  cleaned_lines?: number
  removed?: number
  backed_up?: string
  would_remove?: number
  preview?: string[]
}> {
  const { data } = await api.post('/tools/remove-credits', {
    file_path: filePath,
    dry_run: dryRun,
  })
  return data
}

export async function detectOpeningEnding(filePath: string): Promise<{
  status: string
  detected: Array<{
    type: 'OP' | 'ED'
    start_ms: number
    end_ms: number
    event_count: number
    method: 'style' | 'duration'
  }>
}> {
  const { data } = await api.post('/tools/detect-opening-ending', { file_path: filePath })
  return data
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

// ─── Subtitle Diff ────────────────────────────────────────────────────────────

export async function computeSubtitleDiff(
  original: string,
  modified: string,
): Promise<SubtitleDiffResult> {
  try {
    const { data } = await api.post<SubtitleDiffResult>('/tools/diff', { original, modified })
    return data
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
    throw new Error(msg ?? `computeSubtitleDiff failed`, { cause: err })
  }
}

export async function applySubtitleDiff(
  filePath: string,
  original: string,
  modified: string,
  rejectedIndices: number[],
): Promise<{ status: string; file_path: string; backup: string }> {
  try {
    const { data } = await api.post<{ status: string; file_path: string; backup: string }>(
      '/tools/diff/apply',
      { file_path: filePath, original, modified, rejected_indices: rejectedIndices },
    )
    return data
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
    throw new Error(msg ?? `applySubtitleDiff failed`, { cause: err })
  }
}

// ─── Subtitle Processing ──────────────────────────────────────────────────────

export interface ModConfig {
  mod: 'common_fixes' | 'hi_removal' | 'credit_removal'
  options?: Record<string, unknown>
}

export interface ProcessingChange {
  event_index: number
  timestamp: string
  original_text: string
  modified_text: string
  mod_name: string
}

export interface ProcessingResult {
  changes: ProcessingChange[]
  backed_up: boolean
  output_path: string
  dry_run: boolean
}

export async function processSubtitle(
  path: string,
  mods: ModConfig[],
  dry_run = false
): Promise<ProcessingResult> {
  const res = await fetch('/api/v1/tools/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, mods, dry_run }),
  })
  if (!res.ok) throw new Error((await res.json()).error ?? res.statusText)
  return res.json()
}

export async function undoProcessSubtitle(path: string): Promise<void> {
  const res = await fetch('/api/v1/tools/process/undo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) throw new Error((await res.json()).error ?? res.statusText)
}

export async function checkBakExists(path: string): Promise<boolean> {
  const res = await fetch(`/api/v1/tools/process/bak-exists?path=${encodeURIComponent(path)}`)
  if (!res.ok) return false
  return (await res.json()).exists as boolean
}

export async function getInterjections(): Promise<{ items: string[]; is_custom: boolean }> {
  const res = await fetch('/api/v1/tools/process/interjections')
  if (!res.ok) throw new Error((await res.json()).error ?? res.statusText)
  return res.json()
}

export async function putInterjections(items: string[]): Promise<void> {
  const res = await fetch('/api/v1/tools/process/interjections', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!res.ok) throw new Error((await res.json()).error ?? res.statusText)
}

export async function processSeries(series_id: number): Promise<void> {
  const res = await fetch(`/api/v1/library/series/${series_id}/process`, { method: 'POST' })
  if (!res.ok) throw new Error((await res.json()).error ?? res.statusText)
}

export async function processLibraryAll(filter: 'all' | 'unprocessed' = 'all'): Promise<void> {
  const res = await fetch('/api/v1/library/process-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filter }),
  })
  if (!res.ok) throw new Error((await res.json()).error ?? res.statusText)
}

export async function updateSeriesProcessingConfig(
  series_id: number,
  config: Record<string, boolean | null>
): Promise<void> {
  const res = await fetch(`/api/v1/library/series/${series_id}/processing-config`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error(res.statusText)
}
