import { api } from '../core'
import type {
  SubtitleToolResult,
  SubtitleContent, SubtitleSaveResult, SubtitleBackup, SubtitleValidation, SubtitleParseResult,
  SubtitleDiffResult,
  BazarrMappingReport, CompatBatchResult, ExtendedHealthAllResponse, ExportResult,
} from '@/lib/types'

// ─── Subtitle Tools ───────────────────────────────────────────────────────────

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

// ─── Audio ────────────────────────────────────────────────────────────────────

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

// ─── OCR ──────────────────────────────────────────────────────────────────────

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

// ─── External Integrations ────────────────────────────────────────────────────

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

// ─── Quality Fixes ────────────────────────────────────────────────────────────

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

// ─── Format Conversion ────────────────────────────────────────────────────────

export async function convertSubtitle(params: {
  file_path?: string
  track_index?: number
  video_path?: string
  target_format: 'srt' | 'ass' | 'ssa' | 'vtt'
}): Promise<{ output_path: string; format: string }> {
  const { data } = await api.post('/tools/convert', params)
  return data as { output_path: string; format: string }
}

// ─── Waveform Extraction ──────────────────────────────────────────────────────

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
