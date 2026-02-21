import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  getHealth, getStats, getJobs,
  getBatchStatus, getConfig, updateConfig, getLibrary, getSeriesDetail,
  translateFile, startBatch, getLogs,
  getWantedItems, getWantedSummary, refreshWanted,
  updateWantedItemStatus, deleteWantedItem,
  searchWantedItem, processWantedItem, extractEmbeddedSub,
  startWantedBatchSearch, getWantedBatchStatus,
  getProviders, testProvider, getProviderStats, clearProviderCache,
  searchAllWanted, getRetranslateStatus, retranslateSingle, retranslateBatch,
  getLanguageProfiles, createLanguageProfile, updateLanguageProfile,
  deleteLanguageProfile, assignProfile,
  getBlacklist, addToBlacklist, removeFromBlacklist, clearBlacklist,
  getHistory, getHistoryStats,
  episodeSearch, episodeHistory, retryJob,
  searchInteractive, searchInteractiveEpisode, downloadSpecific, downloadSpecificEpisode,
  exportConfig, importConfig,
  getGlossaryEntries, createGlossaryEntry, updateGlossaryEntry, deleteGlossaryEntry,
  getPromptPresets, getDefaultPromptPreset, createPromptPreset, updatePromptPreset, deletePromptPreset,
  getBackends, testBackend, getBackendConfig, saveBackendConfig, getBackendStats,
  getMediaServerTypes, getMediaServerInstances, saveMediaServerInstances, testMediaServer, getMediaServerHealth,
  getWhisperBackends, testWhisperBackend, getWhisperBackendConfig, saveWhisperBackendConfig,
  getWhisperConfig, saveWhisperConfig, getWhisperQueue, getWhisperStats,
  getWatchedFolders, saveWatchedFolder, deleteWatchedFolder,
  getStandaloneSeries, getStandaloneMovies, triggerStandaloneScan,
  getStandaloneStatus, refreshSeriesMetadata,
  getEventCatalog, getHookConfigs, createHookConfig, updateHookConfig, deleteHookConfig, testHook,
  getWebhookConfigs, createWebhookConfig, updateWebhookConfig, deleteWebhookConfig, testWebhook,
  getHookLogs, clearHookLogs,
  getScoringWeights, updateScoringWeights, resetScoringWeights,
  getProviderModifiers, updateProviderModifiers,
  getStatistics, exportStatistics,
  createFullBackup, listFullBackups, restoreFullBackup,
  getLogRotation, updateLogRotation,
  runSubtitleTool, previewSubtitle,
  getSubtitleContent, saveSubtitleContent, getSubtitleBackup, validateSubtitle, parseSubtitleCues,
  getTasks,
  runHealthCheck, applyHealthFix, getQualityTrends,
  compareSubtitles, advancedSync,
  searchGlobal, getFilterPresets, createFilterPreset, deleteFilterPreset,
  batchAction,
  getApiKeys, updateApiKey, testApiKey, exportApiKeys, importApiKeys,
  importBazarrConfig, confirmBazarrImport,
  getNotificationTemplates, createNotificationTemplate, updateNotificationTemplate, deleteNotificationTemplate,
  previewNotificationTemplate, getTemplateVariables,
  getQuietHours, createQuietHours, updateQuietHours, deleteQuietHours,
  getNotificationHistory, resendNotification,
  getNotificationFilters, updateNotificationFilters,
  getCleanupStats, startCleanupScan, getCleanupScanStatus,
  getDuplicates, deleteDuplicates,
  getMarketplacePlugins, getMarketplacePlugin, installMarketplacePlugin,
  uninstallMarketplacePlugin, checkMarketplaceUpdates,
  scanOrphaned, getOrphanedFiles, deleteOrphaned,
  getCleanupRules, createCleanupRule, updateCleanupRule, deleteCleanupRule, runCleanupRule,
  getCleanupHistory, getCleanupPreview,
  getBazarrMappingReport, runCompatCheck, getExtendedHealthAll,
  exportIntegrationConfig, exportIntegrationConfigZip,
  getWaveform, extractAudio,
  checkSpelling, getSpellDictionaries,
  extractOCR, previewOCRFrame,
} from '@/api/client'
import type {
  LanguageProfile, BackendConfig, MediaServerInstance, HookConfig, WebhookConfig, LogRotationConfig, FilterScope, BatchAction,
  NotificationTemplate, QuietHoursConfig, NotificationFilter, BazarrMigrationPreview,
  CleanupRule,
} from '@/lib/types'
import type { DownloadSpecificPayload } from '@/api/client'

// ─── Health ──────────────────────────────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
  })
}

// ─── Stats ───────────────────────────────────────────────────────────────────

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 30000,
  })
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export function useJobs(page = 1, perPage = 50, status?: string) {
  return useQuery({
    queryKey: ['jobs', page, perPage, status],
    queryFn: () => getJobs(page, perPage, status),
    refetchInterval: 15000,
  })
}

// ─── Batch ───────────────────────────────────────────────────────────────────

export function useBatchStatus() {
  return useQuery({
    queryKey: ['batch-status'],
    queryFn: getBatchStatus,
    refetchInterval: 15000,
  })
}

// ─── Config ──────────────────────────────────────────────────────────────────

export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
    staleTime: 5 * 60_000,
  })
}

export function useUpdateConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => updateConfig(values),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      const keys = Object.keys(variables)
      if (keys.some(k => k.startsWith('sonarr_') || k.startsWith('radarr_'))) {
        queryClient.invalidateQueries({ queryKey: ['library'] })
      }
      if (keys.some(k => k.startsWith('provider_') || k.startsWith('scoring_'))) {
        queryClient.invalidateQueries({ queryKey: ['providers'] })
        queryClient.invalidateQueries({ queryKey: ['provider-stats'] })
      }
    },
  })
}

// ─── Wanted ─────────────────────────────────────────────────────────────

export function useWantedItems(page = 1, perPage = 50, itemType?: string, status?: string, subtitleType?: string) {
  return useQuery({
    queryKey: ['wanted', page, perPage, itemType, status, subtitleType],
    queryFn: () => getWantedItems(page, perPage, itemType, status, subtitleType),
  })
}

export function useWantedSummary() {
  return useQuery({
    queryKey: ['wanted-summary'],
    queryFn: getWantedSummary,
  })
}

export function useRefreshWanted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (seriesId?: number) => refreshWanted(seriesId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
    },
  })
}

export function useUpdateWantedStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, status }: { itemId: number; status: string }) =>
      updateWantedItemStatus(itemId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
    },
  })
}

export function useSearchWantedItem() {
  return useMutation({
    mutationFn: (itemId: number) => searchWantedItem(itemId),
  })
}

export function useProcessWantedItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (itemId: number) => processWantedItem(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
    },
  })
}

export function useExtractEmbeddedSub() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, options }: { itemId: number; options?: { stream_index?: number; target_language?: string } }) =>
      extractEmbeddedSub(itemId, options),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
    },
  })
}

export function useStartWantedBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars?: { itemIds?: number[]; seriesId?: number }) =>
      startWantedBatchSearch(vars?.itemIds, vars?.seriesId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted-batch-status'] })
    },
  })
}

export function useWantedBatchStatus() {
  return useQuery({
    queryKey: ['wanted-batch-status'],
    queryFn: getWantedBatchStatus,
    refetchInterval: 10000,
  })
}

// ─── Providers ───────────────────────────────────────────────────────────────

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: getProviders,
    staleTime: 5 * 60_000,
  })
}

export function useTestProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => testProvider(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useProviderStats() {
  return useQuery({
    queryKey: ['provider-stats'],
    queryFn: getProviderStats,
  })
}

export function useClearProviderCache() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (providerName?: string) => clearProviderCache(providerName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['provider-stats'] })
    },
  })
}

// ─── Language Profiles ───────────────────────────────────────────────────────

export function useLanguageProfiles() {
  return useQuery({
    queryKey: ['language-profiles'],
    queryFn: getLanguageProfiles,
    staleTime: 5 * 60_000,
  })
}

export function useCreateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Omit<LanguageProfile, 'id' | 'is_default'>) => createLanguageProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<LanguageProfile> }) =>
      updateLanguageProfile(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

export function useDeleteProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteLanguageProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

export function useAssignProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ type, arrId, profileId }: { type: 'series' | 'movie'; arrId: number; profileId: number }) =>
      assignProfile(type, arrId, profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

// ─── Blacklist ────────────────────────────────────────────────────────────────

export function useBlacklist(page = 1, perPage = 50) {
  return useQuery({
    queryKey: ['blacklist', page, perPage],
    queryFn: () => getBlacklist(page, perPage),
  })
}

export function useAddToBlacklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      provider_name: string; subtitle_id: string;
      language?: string; file_path?: string; title?: string; reason?: string
    }) => addToBlacklist(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blacklist'] })
    },
  })
}

export function useRemoveFromBlacklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => removeFromBlacklist(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blacklist'] })
    },
  })
}

export function useClearBlacklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => clearBlacklist(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blacklist'] })
    },
  })
}

// ─── History ──────────────────────────────────────────────────────────────────

export function useHistory(page = 1, perPage = 50, provider?: string, language?: string) {
  return useQuery({
    queryKey: ['history', page, perPage, provider, language],
    queryFn: () => getHistory(page, perPage, provider, language),
  })
}

export function useHistoryStats() {
  return useQuery({
    queryKey: ['history-stats'],
    queryFn: getHistoryStats,
  })
}

// ─── Search All ──────────────────────────────────────────────────────────────

export function useSearchAllWanted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => searchAllWanted(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
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

// ─── Mutations ───────────────────────────────────────────────────────────────

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

// ─── Episode Search & History ─────────────────────────────────────────────────

export function useEpisodeSearch() {
  return useMutation({
    mutationFn: (episodeId: number) => episodeSearch(episodeId),
  })
}

export function useEpisodeHistory(episodeId: number) {
  return useQuery({
    queryKey: ['episode-history', episodeId],
    queryFn: () => episodeHistory(episodeId),
    enabled: false,
  })
}

// ─── Interactive Search ───────────────────────────────────────────────────────

export function useSearchInteractive(itemId: number | null, enabled = false) {
  return useQuery({
    queryKey: ['interactive-search', 'wanted', itemId],
    queryFn: () => searchInteractive(itemId!),
    enabled: enabled && !!itemId,
    staleTime: 0,
    gcTime: 5 * 60_000,
  })
}

export function useSearchInteractiveEpisode(episodeId: number | null, enabled = false) {
  return useQuery({
    queryKey: ['interactive-search', 'episode', episodeId],
    queryFn: () => searchInteractiveEpisode(episodeId!),
    enabled: enabled && !!episodeId,
    staleTime: 0,
    gcTime: 5 * 60_000,
  })
}

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

// ─── Job Retry ───────────────────────────────────────────────────────────────

export function useRetryJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => retryJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

// ─── Config Export/Import ────────────────────────────────────────────────────

export function useExportConfig() {
  return useMutation({
    mutationFn: () => exportConfig(),
  })
}

export function useImportConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (config: Record<string, unknown>) => importConfig(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

// ─── Logs ────────────────────────────────────────────────────────────────────

export function useLogs(lines = 200, level?: string) {
  return useQuery({
    queryKey: ['logs', lines, level],
    queryFn: () => getLogs(lines, level),
    refetchInterval: 10000,
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

export function useCreateGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createGlossaryEntry,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['glossary', variables.series_id] })
    },
  })
}

export function useUpdateGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, ...data }: { entryId: number; series_id: number; source_term?: string; target_term?: string; notes?: string }) =>
      updateGlossaryEntry(entryId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['glossary', variables.series_id] })
    },
  })
}

export function useDeleteGlossaryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, seriesId }: { entryId: number; seriesId: number }) =>
      deleteGlossaryEntry(entryId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['glossary', variables.seriesId] })
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

// ─── Media Servers ──────────────────────────────────────────────────────────

export function useMediaServerTypes() {
  return useQuery({
    queryKey: ['mediaServerTypes'],
    queryFn: getMediaServerTypes,
    staleTime: 60_000,
  })
}

export function useMediaServerInstances() {
  return useQuery({
    queryKey: ['mediaServerInstances'],
    queryFn: getMediaServerInstances,
    staleTime: 5 * 60_000,
  })
}

export function useSaveMediaServerInstances() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (instances: MediaServerInstance[]) => saveMediaServerInstances(instances),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mediaServerInstances'] })
    },
  })
}

export function useTestMediaServer() {
  return useMutation({
    mutationFn: (config: Record<string, unknown>) => testMediaServer(config),
  })
}

export function useMediaServerHealth() {
  return useQuery({
    queryKey: ['mediaServerHealth'],
    queryFn: getMediaServerHealth,
    staleTime: 30_000,
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

// ─── Standalone Mode ──────────────────────────────────────────────────────

export function useWatchedFolders() {
  return useQuery({ queryKey: ['watchedFolders'], queryFn: getWatchedFolders })
}

export function useSaveWatchedFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: saveWatchedFolder,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['watchedFolders'] }) },
  })
}

export function useDeleteWatchedFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteWatchedFolder,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['watchedFolders'] }) },
  })
}

export function useStandaloneSeries() {
  return useQuery({ queryKey: ['standaloneSeries'], queryFn: getStandaloneSeries })
}

export function useStandaloneMovies() {
  return useQuery({ queryKey: ['standaloneMovies'], queryFn: getStandaloneMovies })
}

export function useTriggerStandaloneScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerStandaloneScan,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['standaloneSeries'] })
      void qc.invalidateQueries({ queryKey: ['standaloneMovies'] })
    },
  })
}

export function useStandaloneStatus() {
  return useQuery({ queryKey: ['standaloneStatus'], queryFn: getStandaloneStatus })
}

export function useRefreshSeriesMetadata() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: refreshSeriesMetadata,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['standaloneSeries'] }) },
  })
}

// ─── Events & Hooks ──────────────────────────────────────────────────────

export function useEventCatalog() {
  return useQuery({ queryKey: ['eventCatalog'], queryFn: getEventCatalog })
}

export function useHookConfigs() {
  return useQuery({ queryKey: ['hookConfigs'], queryFn: () => getHookConfigs() })
}

export function useCreateHook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createHookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookConfigs'] }) },
  })
}

export function useUpdateHook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<HookConfig> }) => updateHookConfig(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookConfigs'] }) },
  })
}

export function useDeleteHook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteHookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookConfigs'] }) },
  })
}

export function useTestHook() {
  return useMutation({ mutationFn: testHook })
}

export function useWebhookConfigs() {
  return useQuery({ queryKey: ['webhookConfigs'], queryFn: () => getWebhookConfigs() })
}

export function useCreateWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createWebhookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['webhookConfigs'] }) },
  })
}

export function useUpdateWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<WebhookConfig> }) => updateWebhookConfig(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['webhookConfigs'] }) },
  })
}

export function useDeleteWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteWebhookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['webhookConfigs'] }) },
  })
}

export function useTestWebhook() {
  return useMutation({ mutationFn: testWebhook })
}

export function useHookLogs(params?: { hook_id?: number; webhook_id?: number; limit?: number }) {
  return useQuery({ queryKey: ['hookLogs', params], queryFn: () => getHookLogs(params) })
}

export function useClearHookLogs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: clearHookLogs,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookLogs'] }) },
  })
}

export function useScoringWeights() {
  return useQuery({ queryKey: ['scoringWeights'], queryFn: getScoringWeights })
}

export function useUpdateScoringWeights() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateScoringWeights,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['scoringWeights'] }) },
  })
}

export function useResetScoringWeights() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: resetScoringWeights,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['scoringWeights'] }) },
  })
}

export function useProviderModifiers() {
  return useQuery({ queryKey: ['providerModifiers'], queryFn: getProviderModifiers })
}

export function useUpdateProviderModifiers() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateProviderModifiers,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['providerModifiers'] }) },
  })
}

// ─── Statistics ──────────────────────────────────────────────────────────────

export function useStatistics(range: string) {
  return useQuery({
    queryKey: ['statistics', range],
    queryFn: () => getStatistics(range),
    refetchInterval: 60000,
  })
}

export function useExportStatistics() {
  return useMutation({
    mutationFn: ({ range, format }: { range: string; format: 'json' | 'csv' }) =>
      exportStatistics(range, format),
  })
}

// ─── Full Backup ─────────────────────────────────────────────────────────────

export function useFullBackups() {
  return useQuery({
    queryKey: ['full-backups'],
    queryFn: listFullBackups,
  })
}

export function useCreateFullBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createFullBackup,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['full-backups'] }) },
  })
}

export function useRestoreFullBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: restoreFullBackup,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['full-backups'] })
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

// ─── Log Rotation ────────────────────────────────────────────────────────────

export function useLogRotation() {
  return useQuery({
    queryKey: ['log-rotation'],
    queryFn: getLogRotation,
  })
}

export function useUpdateLogRotation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (config: LogRotationConfig) => updateLogRotation(config),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['log-rotation'] }) },
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

// ─── Scheduler Tasks ────────────────────────────────────────────────────────

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: getTasks,
    refetchInterval: 30000,
  })
}

export function useTriggerTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (taskName: string) => {
      // Map task names to their trigger endpoints
      const triggerMap: Record<string, () => Promise<unknown>> = {
        wanted_scan: async () => {
          const { default: api } = await import('@/api/client')
          return api.post('/wanted/refresh').then(r => r.data)
        },
        wanted_search: async () => {
          const { default: api } = await import('@/api/client')
          return api.post('/wanted/search-all').then(r => r.data)
        },
      }
      const trigger = triggerMap[taskName]
      if (!trigger) throw new Error(`Unknown task: ${taskName}`)
      return trigger()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
    },
  })
}

// ─── Health Check ────────────────────────────────────────────────────────────

export function useHealthCheck(filePath: string | null) {
  return useQuery({
    queryKey: ['health-check', filePath],
    queryFn: () => runHealthCheck(filePath!),
    enabled: !!filePath,
    staleTime: 5 * 60 * 1000, // 5 min cache
  })
}

export function useHealthFix() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ filePath, fixes }: { filePath: string; fixes: string[] }) =>
      applyHealthFix(filePath, fixes),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: ['health-check', variables.filePath] })
    },
  })
}

export function useQualityTrends(days?: number) {
  return useQuery({
    queryKey: ['quality-trends', days],
    queryFn: () => getQualityTrends(days),
    staleTime: 10 * 60 * 1000, // 10 min cache
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
    }: {
      filePath: string
      operation: 'offset' | 'speed' | 'framerate'
      params: Record<string, number>
      preview?: boolean
    }) => advancedSync(filePath, operation, params, preview),
  })
}

// ─── Phase 12: Search + Filter Presets + Batch Actions ────────────────────

export function useGlobalSearch(query: string) {
  const [debouncedQuery, setDebouncedQuery] = useState(query)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(timer)
  }, [query])

  return useQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: () => searchGlobal(debouncedQuery),
    enabled: debouncedQuery.trim().length >= 2,
    staleTime: 10_000,
    placeholderData: keepPreviousData,
  })
}

export function useFilterPresets(scope: FilterScope) {
  return useQuery({
    queryKey: ['filter-presets', scope],
    queryFn: () => getFilterPresets(scope),
    staleTime: 60_000,
  })
}

export function useCreateFilterPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (preset: Parameters<typeof createFilterPreset>[0]) => createFilterPreset(preset),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ['filter-presets', data.scope] }),
  })
}

export function useDeleteFilterPreset(scope: FilterScope) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteFilterPreset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['filter-presets', scope] }),
  })
}

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

// ─── API Key Management ──────────────────────────────────────────────────────

export function useApiKeys() {
  return useQuery({
    queryKey: ['api-keys'],
    queryFn: getApiKeys,
    staleTime: 30_000,
  })
}

export function useUpdateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ service, keyName, value }: { service: string; keyName: string; value: string }) =>
      updateApiKey(service, keyName, value),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['api-keys'] }) },
  })
}

export function useTestApiKey() {
  return useMutation({
    mutationFn: (service: string) => testApiKey(service),
  })
}

export function useExportApiKeys() {
  return useMutation({
    mutationFn: () => exportApiKeys(),
  })
}

export function useImportApiKeys() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => importApiKeys(file),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['api-keys'] }) },
  })
}

export function useBazarrMigration() {
  return useMutation({
    mutationFn: (file: File) => importBazarrConfig(file),
  })
}

export function useConfirmBazarrImport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (preview: BazarrMigrationPreview) => confirmBazarrImport(preview),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['api-keys'] })
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

// ─── Notification Templates ──────────────────────────────────────────────────

export function useNotificationTemplates() {
  return useQuery({
    queryKey: ['notification-templates'],
    queryFn: getNotificationTemplates,
    staleTime: 30_000,
  })
}

export function useCreateNotificationTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (template: Partial<NotificationTemplate>) => createNotificationTemplate(template),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-templates'] }) },
  })
}

export function useUpdateNotificationTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<NotificationTemplate> }) =>
      updateNotificationTemplate(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-templates'] }) },
  })
}

export function useDeleteNotificationTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteNotificationTemplate(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-templates'] }) },
  })
}

export function usePreviewNotificationTemplate() {
  return useMutation({
    mutationFn: (id: number) => previewNotificationTemplate(id),
  })
}

export function useTemplateVariables(eventType?: string) {
  return useQuery({
    queryKey: ['template-variables', eventType],
    queryFn: () => getTemplateVariables(eventType),
    staleTime: 60_000,
  })
}

export function useQuietHours() {
  return useQuery({
    queryKey: ['quiet-hours'],
    queryFn: getQuietHours,
    staleTime: 30_000,
  })
}

export function useCreateQuietHours() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (config: Partial<QuietHoursConfig>) => createQuietHours(config),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['quiet-hours'] }) },
  })
}

export function useUpdateQuietHours() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<QuietHoursConfig> }) =>
      updateQuietHours(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['quiet-hours'] }) },
  })
}

export function useDeleteQuietHours() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteQuietHours(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['quiet-hours'] }) },
  })
}

export function useNotificationHistory(page = 1, eventType?: string) {
  return useQuery({
    queryKey: ['notification-history', page, eventType],
    queryFn: () => getNotificationHistory(page, eventType),
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  })
}

export function useResendNotification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => resendNotification(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-history'] }) },
  })
}

export function useNotificationFilters() {
  return useQuery({
    queryKey: ['notification-filters'],
    queryFn: getNotificationFilters,
    staleTime: 60_000,
  })
}

export function useUpdateNotificationFilters() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filters: NotificationFilter) => updateNotificationFilters(filters),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-filters'] }) },
  })
}

// ─── Cleanup System ─────────────────────────────────────────────────────────

export function useCleanupStats() {
  return useQuery({
    queryKey: ['cleanup-stats'],
    queryFn: getCleanupStats,
    staleTime: 30_000,
  })
}

export function useStartCleanupScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: startCleanupScan,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cleanup-scan-status'] }) },
  })
}

export function useCleanupScanStatus(enabled = false) {
  return useQuery({
    queryKey: ['cleanup-scan-status'],
    queryFn: getCleanupScanStatus,
    refetchInterval: enabled ? 5000 : false,
    enabled,
  })
}

export function useDuplicates(page = 1) {
  return useQuery({
    queryKey: ['cleanup-duplicates', page],
    queryFn: () => getDuplicates(page),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}

export function useDeleteDuplicates() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (selections: { keep: string; delete: string[] }[]) => deleteDuplicates(selections),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cleanup-duplicates'] })
      void qc.invalidateQueries({ queryKey: ['cleanup-stats'] })
    },
  })
}

export function useOrphanedScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: scanOrphaned,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cleanup-orphaned'] }) },
  })
}

export function useOrphanedFiles() {
  return useQuery({
    queryKey: ['cleanup-orphaned'],
    queryFn: getOrphanedFiles,
    staleTime: 30_000,
  })
}

export function useDeleteOrphaned() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filePaths: string[]) => deleteOrphaned(filePaths),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cleanup-orphaned'] })
      void qc.invalidateQueries({ queryKey: ['cleanup-stats'] })
    },
  })
}

export function useCleanupRules() {
  return useQuery({
    queryKey: ['cleanup-rules'],
    queryFn: getCleanupRules,
    staleTime: 60_000,
  })
}

export function useCreateCleanupRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rule: Omit<CleanupRule, 'id' | 'last_run_at' | 'created_at'>) => createCleanupRule(rule),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cleanup-rules'] }) },
  })
}

export function useUpdateCleanupRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<CleanupRule> }) => updateCleanupRule(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cleanup-rules'] }) },
  })
}

export function useDeleteCleanupRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteCleanupRule(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cleanup-rules'] }) },
  })
}

export function useRunCleanupRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => runCleanupRule(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cleanup-rules'] })
      void qc.invalidateQueries({ queryKey: ['cleanup-stats'] })
      void qc.invalidateQueries({ queryKey: ['cleanup-history'] })
    },
  })
}

export function useCleanupHistory(page = 1) {
  return useQuery({
    queryKey: ['cleanup-history', page],
    queryFn: () => getCleanupHistory(page),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}

export function useCleanupPreview() {
  return useMutation({
    mutationFn: (ruleId?: number) => getCleanupPreview(ruleId),
  })
}

// ─── External Integrations ──────────────────────────────────────────────────

export function useBazarrMappingReport() {
  return useMutation({
    mutationFn: (dbPath: string) => getBazarrMappingReport(dbPath),
  })
}

export function useCompatCheck() {
  return useMutation({
    mutationFn: ({ subtitlePaths, videoPath, target }: { subtitlePaths: string[]; videoPath: string; target: string }) =>
      runCompatCheck(subtitlePaths, videoPath, target),
  })
}

export function useExtendedHealthAll() {
  return useQuery({
    queryKey: ['extended-health-all'],
    queryFn: getExtendedHealthAll,
    enabled: false,
  })
}

export function useExportIntegrationConfig() {
  return useMutation({
    mutationFn: ({ format, includeSecrets }: { format: string; includeSecrets: boolean }) =>
      exportIntegrationConfig(format, includeSecrets),
  })
}

export function useExportIntegrationConfigZip() {
  return useMutation({
    mutationFn: ({ formats, includeSecrets }: { formats: string[]; includeSecrets: boolean }) =>
      exportIntegrationConfigZip(formats, includeSecrets),
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

// ─── Marketplace ────────────────────────────────────────────────────────────────

export function useMarketplacePlugins(category?: string) {
  return useQuery({
    queryKey: ['marketplace', 'plugins', category],
    queryFn: () => getMarketplacePlugins(category),
  })
}

export function useMarketplacePlugin(pluginName: string) {
  return useQuery({
    queryKey: ['marketplace', 'plugin', pluginName],
    queryFn: () => getMarketplacePlugin(pluginName),
    enabled: !!pluginName,
  })
}

export function useInstallMarketplacePlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pluginName, version }: { pluginName: string; version?: string }) =>
      installMarketplacePlugin(pluginName, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace'] })
    },
  })
}

export function useUninstallMarketplacePlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (pluginName: string) => uninstallMarketplacePlugin(pluginName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace'] })
    },
  })
}

export function useCheckMarketplaceUpdates(installedPlugins: string[]) {
  return useQuery({
    queryKey: ['marketplace', 'updates', installedPlugins],
    queryFn: () => checkMarketplaceUpdates(installedPlugins),
    enabled: installedPlugins.length > 0,
  })
}
