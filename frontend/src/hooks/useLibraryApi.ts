import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getLibrary, getSeriesDetail,
  getSeriesAudioPref, setSeriesAudioPref,
  runSubtitleTool, previewSubtitle,
  getSubtitleContent, saveSubtitleContent, getSubtitleBackup, validateSubtitle, parseSubtitleCues,
  compareSubtitles, advancedSync,
  getWaveform, extractAudio,
  checkSpelling, getSpellDictionaries,
  extractOCR, previewOCRFrame,
  getVideoChapters,
  getStreamingEnabled,
  batchAction,
  getSeriesFansubPrefs, setSeriesFansubPrefs, deleteSeriesFansubPrefs,
  updateSeriesSettings,
} from '@/api/client'
import type { BatchAction } from '@/lib/types'

// ─── Library ─────────────────────────────────────────────────────────────────

export function useLibrary() {
  return useQuery({
    queryKey: ['library'],
    queryFn: getLibrary,
    staleTime: 60_000,
  })
}

export function useSeriesDetail(seriesId: number) {
  return useQuery({
    queryKey: ['series', seriesId],
    queryFn: () => getSeriesDetail(seriesId),
    enabled: !!seriesId,
  })
}

// ─── Series Audio Track Preference ────────────────────────────────────────

export function useSeriesAudioPref(seriesId: number) {
  return useQuery({
    queryKey: ['series-audio-pref', seriesId],
    queryFn: () => getSeriesAudioPref(seriesId),
  })
}

export function useSetSeriesAudioPref(seriesId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (trackIndex: number | null) => setSeriesAudioPref(seriesId, trackIndex),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['series-audio-pref', seriesId] }) },
  })
}

// ─── Subtitle Tools ──────────────────────────────────────────────────────────

export function useSubtitleTool() {
  return useMutation({
    mutationFn: ({ tool, params }: { tool: string; params: Record<string, unknown> }) =>
      runSubtitleTool(tool, params),
  })
}

export function usePreviewSubtitle() {
  return useMutation({
    mutationFn: (filePath: string) => previewSubtitle(filePath),
  })
}

export function useSubtitleContent(filePath: string | null) {
  return useQuery({
    queryKey: ['subtitle-content', filePath],
    queryFn: () => getSubtitleContent(filePath!),
    enabled: !!filePath,
    staleTime: 30_000,  // 30s cache — user can manually refresh if needed
  })
}

export function useSubtitleParse(filePath: string | null) {
  return useQuery({
    queryKey: ['subtitle-parse', filePath],
    queryFn: () => parseSubtitleCues(filePath!),
    enabled: !!filePath,
    staleTime: 30_000,  // Cue data unlikely to change frequently
  })
}

export function useSubtitleBackup(filePath: string | null) {
  return useQuery({
    queryKey: ['subtitle-backup', filePath],
    queryFn: () => getSubtitleBackup(filePath!),
    enabled: !!filePath,
  })
}

export function useSaveSubtitle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ filePath, content, lastModified }: { filePath: string; content: string; lastModified: number }) =>
      saveSubtitleContent(filePath, content, lastModified),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['subtitle-content', variables.filePath] })
      queryClient.invalidateQueries({ queryKey: ['subtitle-backup', variables.filePath] })
    },
  })
}

export function useValidateSubtitle() {
  return useMutation({
    mutationFn: ({ content, format, filePath }: { content: string; format?: string; filePath?: string }) =>
      validateSubtitle(content, format, filePath),
  })
}

// ─── Comparison ──────────────────────────────────────────────────────────────

export function useCompareSubtitles() {
  return useMutation({
    mutationFn: (filePaths: string[]) => compareSubtitles(filePaths),
  })
}

// ─── Sync ────────────────────────────────────────────────────────────────────

export function useAdvancedSync() {
  return useMutation({
    mutationFn: ({
      filePath,
      operation,
      params,
      preview,
      chapterRange,
    }: {
      filePath: string
      operation: 'offset' | 'speed' | 'framerate'
      params: Record<string, number>
      preview?: boolean
      chapterRange?: { start_ms: number; end_ms: number }
    }) => advancedSync(filePath, operation, params, preview, chapterRange),
  })
}

// ─── Audio ────────────────────────────────────────────────────────────────────

export function useWaveform(
  filePath: string | null,
  videoPath: string | null,
  audioTrackIndex?: number,
  enabled = true,
) {
  return useQuery({
    queryKey: ['waveform', filePath, videoPath, audioTrackIndex],
    queryFn: () => {
      if (!videoPath) throw new Error('Video path required')
      return getWaveform(videoPath, audioTrackIndex)
    },
    enabled: enabled && !!videoPath,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export function useExtractAudio() {
  return useMutation({
    mutationFn: ({ filePath, audioTrackIndex }: { filePath: string; audioTrackIndex?: number }) =>
      extractAudio(filePath, audioTrackIndex),
  })
}

// ─── Spell Checking ───────────────────────────────────────────────────────────

export function useSpellCheck() {
  return useMutation({
    mutationFn: ({
      filePath,
      content,
      language,
      customWords,
    }: {
      filePath?: string
      content?: string
      language?: string
      customWords?: string[]
    }) => checkSpelling(filePath, content, language, customWords),
  })
}

export function useSpellDictionaries() {
  return useQuery({
    queryKey: ['spell-dictionaries'],
    queryFn: async () => {
      const result = await getSpellDictionaries()
      return result.dictionaries
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
  })
}

// ─── OCR ───────────────────────────────────────────────────────────────────────

export function useExtractOCR() {
  return useMutation({
    mutationFn: ({
      filePath,
      streamIndex,
      language,
      startTime,
      endTime,
      interval,
    }: {
      filePath: string
      streamIndex: number
      language?: string
      startTime?: number
      endTime?: number
      interval?: number
    }) => extractOCR(filePath, streamIndex, language, startTime, endTime, interval),
  })
}

export function usePreviewOCRFrame() {
  return useMutation({
    mutationFn: ({
      filePath,
      timestamp,
      streamIndex,
    }: {
      filePath: string
      timestamp: number
      streamIndex?: number
    }) => previewOCRFrame(filePath, timestamp, streamIndex),
  })
}

// ─── v0.24.4 Chapter Sync ────────────────────────────────────────────────────

export function useVideoChapters(videoPath: string | undefined) {
  return useQuery({
    queryKey: ['video-chapters', videoPath],
    queryFn: () => getVideoChapters(videoPath!),
    enabled: !!videoPath,
    staleTime: 5 * 60 * 1000, // chapters rarely change — 5 min cache
  })
}

// ─── v0.29.0 Web Player ───────────────────────────────────────────────────────

export function useStreamingEnabled() {
  return useQuery({
    queryKey: ['streaming-enabled'],
    queryFn: getStreamingEnabled,
    staleTime: 60_000,
  })
}

// ─── Batch Actions ───────────────────────────────────────────────────────────

export function useBatchAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemIds, action }: { itemIds: number[]; action: BatchAction }) =>
      batchAction(itemIds, action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['library'] })
    },
  })
}

// ─── Fansub Preferences ──────────────────────────────────────────────────────

export function useSeriesFansubPrefs(seriesId: number) {
  return useQuery({
    queryKey: ['series-fansub-prefs', seriesId],
    queryFn: () => getSeriesFansubPrefs(seriesId),
  })
}

export function useSetSeriesFansubPrefs(seriesId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (prefs: { preferred_groups: string[]; excluded_groups: string[]; bonus: number }) =>
      setSeriesFansubPrefs(seriesId, prefs),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['series-fansub-prefs', seriesId] })
    },
  })
}

export function useDeleteSeriesFansubPrefs(seriesId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => deleteSeriesFansubPrefs(seriesId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['series-fansub-prefs', seriesId] })
    },
  })
}

// --- Phase 25-02: AniDB Absolute Episode Order ---

export function useUpdateSeriesSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ seriesId, settings }: { seriesId: number; settings: { absolute_order: boolean } }) =>
      updateSeriesSettings(seriesId, settings),
    onSuccess: (_, { seriesId }) => {
      queryClient.invalidateQueries({ queryKey: ['series', seriesId] })
    },
  })
}
