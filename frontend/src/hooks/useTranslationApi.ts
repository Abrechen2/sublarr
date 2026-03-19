import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  translateFile, startBatch,
  getRetranslateStatus, retranslateSingle, retranslateBatch,
  getGlossaryEntries, createGlossaryEntry, updateGlossaryEntry, deleteGlossaryEntry,
  suggestGlossaryTerms, exportGlossaryTsv,
  getPromptPresets, getDefaultPromptPreset, createPromptPreset, updatePromptPreset, deletePromptPreset,
  getBackends, testBackend, getBackendConfig, saveBackendConfig, getBackendStats,
  getWhisperBackends, testWhisperBackend, getWhisperBackendConfig, saveWhisperBackendConfig,
  getWhisperConfig, saveWhisperConfig, getWhisperQueue, getWhisperStats,
  downloadSpecific, downloadSpecificEpisode,
  getTranslationMemoryStats, clearTranslationMemoryCache,
  getBackendTemplates,
  batchTranslate,
} from '@/api/client'
import type { BackendConfig } from '@/lib/types'
import type { DownloadSpecificPayload } from '@/api/client'

// ─── Translation Mutations ───────────────────────────────────────────────────

export function useTranslateFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ filePath, force }: { filePath: string; force?: boolean }) =>
      translateFile(filePath, force),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}

export function useStartBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ directory, force, dryRun }: { directory: string; force?: boolean; dryRun?: boolean }) =>
      startBatch(directory, force, dryRun),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batch-status'] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

// ─── Re-Translation ──────────────────────────────────────────────────────────

export function useRetranslateStatus() {
  return useQuery({
    queryKey: ['retranslate-status'],
    queryFn: getRetranslateStatus,
    refetchInterval: 60000,
  })
}

export function useRetranslateSingle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (itemId: number) => retranslateSingle(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['retranslate-status'] })
    },
  })
}

export function useRetranslateBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => retranslateBatch(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['retranslate-status'] })
    },
  })
}

// ─── Glossary ──────────────────────────────────────────────────────────────────

export function useGlossaryEntries(seriesId: number, query?: string) {
  return useQuery({
    queryKey: ['glossary', seriesId, query],
    queryFn: () => getGlossaryEntries(seriesId, query),
    enabled: !!seriesId,
  })
}

export function useGlobalGlossaryEntries() {
  return useQuery({
    queryKey: ['glossary', 'global'],
    queryFn: () => getGlossaryEntries(null),
  })
}

export function useCreateGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createGlossaryEntry,
    onSuccess: (_, variables) => {
      if (variables.series_id != null) {
        queryClient.invalidateQueries({ queryKey: ['glossary', variables.series_id] })
      } else {
        queryClient.invalidateQueries({ queryKey: ['glossary', 'global'] })
      }
    },
  })
}

export function useUpdateGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, ...data }: { entryId: number; series_id?: number | null; source_term?: string; target_term?: string; notes?: string }) =>
      updateGlossaryEntry(entryId, data),
    onSuccess: (_, variables) => {
      if (variables.series_id != null) {
        queryClient.invalidateQueries({ queryKey: ['glossary', variables.series_id] })
      } else {
        queryClient.invalidateQueries({ queryKey: ['glossary', 'global'] })
      }
    },
  })
}

export function useDeleteGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, seriesId: _seriesId }: { entryId: number; seriesId?: number | null }) =>
      deleteGlossaryEntry(entryId),
    onSuccess: (_, variables) => {
      if (variables.seriesId != null) {
        queryClient.invalidateQueries({ queryKey: ['glossary', variables.seriesId] })
      } else {
        queryClient.invalidateQueries({ queryKey: ['glossary', 'global'] })
      }
    },
  })
}

export function useSuggestGlossaryTerms() {
  return useMutation({
    mutationFn: ({ seriesId, options }: {
      seriesId: number
      options?: { source_lang?: string; min_freq?: number }
    }) => suggestGlossaryTerms(seriesId, options),
  })
}

export function useExportGlossaryTsv() {
  return useMutation({
    mutationFn: ({ seriesId }: { seriesId?: number | null }) => exportGlossaryTsv(seriesId),
    onSuccess: (blob, { seriesId }) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = seriesId != null ? `glossary_series_${seriesId}.tsv` : 'glossary_global.tsv'
      a.click()
      URL.revokeObjectURL(url)
    },
  })
}

export function useApproveGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId }: { entryId: number; seriesId?: number | null }) =>
      updateGlossaryEntry(entryId, { approved: 1 }),
    onSuccess: (_, { seriesId }) => {
      queryClient.invalidateQueries({ queryKey: ['glossary', seriesId] })
      queryClient.invalidateQueries({ queryKey: ['glossary', 'global'] })
    },
  })
}

// ─── Prompt Presets ───────────────────────────────────────────────────────────

export function usePromptPresets() {
  return useQuery({
    queryKey: ['prompt-presets'],
    queryFn: () => getPromptPresets(),
  })
}

export function useDefaultPromptPreset() {
  return useQuery({
    queryKey: ['prompt-presets', 'default'],
    queryFn: getDefaultPromptPreset,
  })
}

export function useCreatePromptPreset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createPromptPreset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt-presets'] })
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

export function useUpdatePromptPreset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ presetId, ...data }: { presetId: number; name?: string; prompt_template?: string; is_default?: boolean }) =>
      updatePromptPreset(presetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt-presets'] })
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

export function useDeletePromptPreset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deletePromptPreset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt-presets'] })
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

// ─── Translation Backends ────────────────────────────────────────────────────

export function useBackends() {
  return useQuery({
    queryKey: ['backends'],
    queryFn: getBackends,
    staleTime: 5 * 60_000,
  })
}

export function useTestBackend() {
  return useMutation({
    mutationFn: (name: string) => testBackend(name),
  })
}

export function useBackendConfig(name: string) {
  return useQuery({
    queryKey: ['backend-config', name],
    queryFn: () => getBackendConfig(name),
    enabled: !!name,
    staleTime: 5 * 60_000,
  })
}

export function useSaveBackendConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, config }: { name: string; config: BackendConfig }) =>
      saveBackendConfig(name, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backends'] })
      queryClient.invalidateQueries({ queryKey: ['backend-config'] })
    },
  })
}

export function useBackendStats() {
  return useQuery({
    queryKey: ['backend-stats'],
    queryFn: getBackendStats,
    staleTime: 60000,
  })
}

// ─── Whisper Hooks ──────────────────────────────────────────────────────────
export function useWhisperBackends() {
  return useQuery({ queryKey: ['whisper-backends'], queryFn: getWhisperBackends })
}
export function useTestWhisperBackend() {
  return useMutation({ mutationFn: (name: string) => testWhisperBackend(name) })
}
export function useWhisperBackendConfig(name: string) {
  return useQuery({
    queryKey: ['whisper-backend-config', name],
    queryFn: () => getWhisperBackendConfig(name),
    enabled: !!name,
  })
}
export function useSaveWhisperBackendConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, config }: { name: string; config: Record<string, string> }) => saveWhisperBackendConfig(name, config),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['whisper-backends'] }) },
  })
}
export function useWhisperConfig() {
  return useQuery({ queryKey: ['whisper-config'], queryFn: getWhisperConfig })
}
export function useSaveWhisperConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (config: Record<string, unknown>) => saveWhisperConfig(config),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['whisper-config'] }) },
  })
}
export function useWhisperQueue(params?: { status?: string; limit?: number }) {
  return useQuery({ queryKey: ['whisper-queue', params], queryFn: () => getWhisperQueue(params), refetchInterval: 15000 })
}
export function useWhisperStats() {
  return useQuery({ queryKey: ['whisper-stats'], queryFn: getWhisperStats })
}

// ─── Download Specific ───────────────────────────────────────────────────────

export function useDownloadSpecific() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: number; payload: DownloadSpecificPayload }) =>
      downloadSpecific(itemId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['wanted-summary'] })
    },
  })
}

export function useDownloadSpecificEpisode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ episodeId, payload }: { episodeId: number; payload: DownloadSpecificPayload }) =>
      downloadSpecificEpisode(episodeId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['series'] })
    },
  })
}

// --- Phase 20-02: Translation Memory ---

export function useTranslationMemoryStats() {
  return useQuery({
    queryKey: ['translation-memory-stats'],
    queryFn: getTranslationMemoryStats,
    staleTime: 30_000,
  })
}

export function useClearTranslationMemoryCache() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => clearTranslationMemoryCache(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['translation-memory-stats'] })
    },
  })
}

// --- Phase 28-01: LLM Backend Presets ---

export function useBackendTemplates() {
  return useQuery({
    queryKey: ['backend-templates'],
    queryFn: getBackendTemplates,
    staleTime: Infinity,
  })
}

// ─── Batch Translate ─────────────────────────────────────────────────────────

export function useBatchTranslate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (itemIds: number[]) => batchTranslate(itemIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
    },
  })
}
