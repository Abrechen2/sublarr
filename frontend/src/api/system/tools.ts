import { api } from '../core'
import type {
  SubtitleToolResult,
  SubtitleContent, SubtitleSaveResult, SubtitleBackupContent, SubtitleValidation, SubtitleParseResult,
  SubtitleDiffResult,
  BazarrMappingReport, CompatBatchResult, ExtendedHealthAllResponse, ExportResult,
} from '@/lib/types'

// â”€â”€â”€ Subtitle Tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

export async function getSubtitleBackup(filePath: string): Promise<SubtitleBackupContent> {
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

// â”€â”€â”€ Audio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Spell Checking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ OCR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ External Integrations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Quality Fixes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Format Conversion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export async function convertSubtitle(params: {
  file_path?: string
  track_index?: number
  video_path?: string
  target_format: 'srt' | 'ass' | 'ssa' | 'vtt'
}): Promise<{ output_path: string; format: string }> {
  const { data } = await api.post('/tools/convert', params)
  return data as { output_path: string; format: string }
}

// â”€â”€â”€ Waveform Extraction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export async function extractWaveform(
  videoPath: string,
  trackIndex?: number,
): Promise<{ audio_url: string; duration_s: number }> {
  const body: { video_path: string; track_index?: number } = { video_path: videoPath }
  if (trackIndex !== undefined) body.track_index = trackIndex
  const { data } = await api.post('/tools/waveform-extract', body)
  return data as { audio_url: string; duration_s: number }
}

// â”€â”€â”€ Audio Tracks (Plan B8) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface AudioTrack {
  index: number
  codec_type: 'audio'
  codec: string
  channels: number
  language: string
  title: string
  default: boolean
  forced: boolean
}

export interface AudioTracksResponse {
  tracks: AudioTrack[]
  video_path: string
}

export async function fetchAudioTracks(videoPath: string): Promise<AudioTracksResponse> {
  const { data } = await api.get<AudioTracksResponse>('/audio/tracks', {
    params: { file_path: videoPath },
  })
  return data
}

export interface KeyframesResponse {
  keyframes: number[]
  video_path: string
}

export async function fetchKeyframes(videoPath: string): Promise<KeyframesResponse> {
  const { data } = await api.get<KeyframesResponse>('/audio/keyframes', {
    params: { file_path: videoPath },
  })
  return data
}

export interface ScenesResponse {
  scenes: number[]
  available: boolean
}

export async function fetchScenes(videoPath: string): Promise<ScenesResponse> {
  const { data } = await api.get<ScenesResponse>('/audio/scenes', {
    params: { file_path: videoPath },
  })
  return data
}

// â”€â”€â”€ Subtitle Diff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Subtitle Processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
  const { data } = await api.post('/tools/process', { path, mods, dry_run })
  return data
}

export async function undoProcessSubtitle(path: string): Promise<void> {
  await api.post('/tools/process/undo', { path })
}

export async function checkBakExists(path: string): Promise<boolean> {
  try {
    const { data } = await api.get('/tools/process/bak-exists', { params: { path } })
    return data.exists as boolean
  } catch {
    return false
  }
}

export async function getInterjections(): Promise<{ items: string[]; is_custom: boolean }> {
  const { data } = await api.get('/tools/process/interjections')
  return data
}

export async function putInterjections(items: string[]): Promise<void> {
  await api.put('/tools/process/interjections', { items })
}

export async function processSeries(series_id: number): Promise<void> {
  await api.post(`/library/series/${series_id}/process`)
}

export async function processLibraryAll(filter: 'all' | 'unprocessed' = 'all'): Promise<void> {
  await api.post('/library/process-all', { filter })
}

export async function updateSeriesProcessingConfig(
  series_id: number,
  config: Record<string, boolean | null>
): Promise<void> {
  await api.patch(`/library/series/${series_id}/processing-config`, config)
}
