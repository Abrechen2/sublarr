import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { toast } from '@/components/shared/Toast'
import { getSetupStatus, completeSetup, type SetupProfile } from '@/api/health'
import {
  getBudgetState,
  getHealth, getUpdateInfo, getStats, getJobs,
  getBatchStatus, getConfig, updateConfig, disableTranslation,
  getLogs,
  retryJob,
  exportConfig, importConfig,
  getWatchedFolders, saveWatchedFolder, deleteWatchedFolder,
  getStandaloneSeries, getStandaloneMovies, triggerStandaloneScan, triggerStandaloneFolderScan,
  getStandaloneStatus, refreshSeriesMetadata,
  getStatistics, exportStatistics,
  createFullBackup, listFullBackups, restoreFullBackup,
  getLogRotation, updateLogRotation,
  getTasks,
  runHealthCheck, applyHealthFix, getQualityTrends,
  searchGlobal, getFilterPresets, createFilterPreset, deleteFilterPreset,
  getApiKeys, updateApiKey, testApiKey, exportApiKeys, importApiKeys,
  getNotificationTemplates, createNotificationTemplate, updateNotificationTemplate, deleteNotificationTemplate,
  previewNotificationTemplate, getTemplateVariables,
  getQuietHours, createQuietHours, updateQuietHours, deleteQuietHours,
  getNotificationHistory, resendNotification,
  getNotificationFilters, updateNotificationFilters,
  getCleanupStats, startCleanupScan, getCleanupScanStatus,
  getDuplicates, deleteDuplicates,
  scanOrphaned, getOrphanedFiles, deleteOrphaned,
  getCleanupRules, createCleanupRule, updateCleanupRule, deleteCleanupRule, runCleanupRule, previewCleanupRule,
  getCleanupHistory, getCleanupPreview,
  getSupportedLanguages,
  testSonarrInstance, testRadarrInstance,
  getFfprobeStats, triggerFfprobeCleanup, triggerDbVacuum,
  getActivity,
} from '@/api/client'
import type {
  LogRotationConfig, FilterScope,
  NotificationTemplate, QuietHoursConfig, NotificationFilter,
  CleanupRule,
} from '@/lib/types'

// ─── Languages ───────────────────────────────────────────────────────────────

export function useSupportedLanguages() {
  return useQuery({
    queryKey: ['languages'],
    queryFn: getSupportedLanguages,
    staleTime: Infinity,
  })
}

// ─── Health ──────────────────────────────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
  })
}

export function useUpdateInfo() {
  const sixHours = 6 * 60 * 60 * 1000
  return useQuery({
    queryKey: ['update-info'],
    queryFn: getUpdateInfo,
    staleTime: sixHours,
    refetchInterval: sixHours,
    retry: 1,
  })
}

// ─── Stats ───────────────────────────────────────────────────────────────────

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    staleTime: 60_000,
  })
}

// ─── Budget State ────────────────────────────────────────────────────────────

export function useBudgetState() {
  return useQuery({
    queryKey: ['system', 'budget'],
    queryFn: getBudgetState,
    refetchInterval: 5_000,
    staleTime: 2_000,
  })
}

// ─── First-run Setup Wizard ──────────────────────────────────────────────────

export function useSetupStatus() {
  return useQuery({
    queryKey: ['system', 'setup', 'status'],
    queryFn: getSetupStatus,
    staleTime: 60_000,
    retry: 0,
  })
}

export function useCompleteSetup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (profile: SetupProfile) => completeSetup(profile),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['system', 'setup', 'status'] })
      void queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export function useJobs(page = 1, perPage = 50, status?: string, refetchMs = 15000) {
  return useQuery({
    queryKey: ['jobs', page, perPage, status],
    queryFn: () => getJobs(page, perPage, status),
    refetchInterval: refetchMs,
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
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: ['config'] })
      const previous = queryClient.getQueryData<Record<string, unknown>>(['config'])
      queryClient.setQueryData<Record<string, unknown>>(['config'], (old) => ({
        ...old,
        ...variables,
      }))
      return { previous }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(['config'], context.previous)
      }
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      const keys = Object.keys(variables)
      if (keys.some(k => k.startsWith('sonarr_') || k.startsWith('radarr_'))) {
        queryClient.invalidateQueries({ queryKey: ['library'] })
      }
      if (keys.some(k => k.startsWith('provider') || k.startsWith('scoring_'))) {
        queryClient.invalidateQueries({ queryKey: ['providers'] })
        queryClient.invalidateQueries({ queryKey: ['provider-stats'] })
      }
    },
  })
}

/** Returns whether the translation feature is enabled. */
export function useTranslationEnabled(): boolean {
  const { data } = useConfig()
  return Boolean(data?.translation_enabled)
}

/** Mutation: disables translation + cancels all queued jobs. */
export function useDisableTranslation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: disableTranslation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useContextWindowSize() {
  const { data } = useConfig()
  const update = useUpdateConfig()
  const value = data ? Number((data as Record<string, unknown>)['translation.context_window_size'] ?? 3) : 3
  const save = (size: number) => update.mutate({ 'translation.context_window_size': String(size) })
  return { value, save, isPending: update.isPending }
}

// ─── Logs ────────────────────────────────────────────────────────────────────

export function useLogs(lines = 200, level?: string) {
  return useQuery({
    queryKey: ['logs', lines, level],
    queryFn: () => getLogs(lines, level),
    refetchInterval: 10000,
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

// ─── Sonarr / Radarr Test ────────────────────────────────────────────────────

export function useTestSonarrInstance() {
  return useMutation({
    mutationFn: (config: { url: string; api_key: string }) => testSonarrInstance(config),
  })
}

export function useTestRadarrInstance() {
  return useMutation({
    mutationFn: (config: { url: string; api_key: string }) => testRadarrInstance(config),
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

export function useTriggerStandaloneFolderScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (folderId: number) => triggerStandaloneFolderScan(folderId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['standaloneSeries'] })
      void qc.invalidateQueries({ queryKey: ['standaloneMovies'] })
      void qc.invalidateQueries({ queryKey: ['watchedFolders'] })
    },
  })
}

export function useStandaloneStatus() {
  return useQuery({
    queryKey: ['standaloneStatus'],
    queryFn: getStandaloneStatus,
    refetchInterval: (query) => (query.state.data?.scanner_scanning ? 2000 : 15000),
  })
}

export function useRefreshSeriesMetadata() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: refreshSeriesMetadata,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['standaloneSeries'] }) },
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

// ─── Scheduler Tasks ────────────────────────────────────────────────────────

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: getTasks,
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? []
      return tasks.some((t: { running: boolean }) => t.running) ? 3000 : 30000
    },
  })
}

export function useTriggerTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (taskName: string) => {
      const { default: api } = await import('@/api/client')
      // Map task names to their trigger endpoints
      const triggerMap: Record<string, () => Promise<unknown>> = {
        wanted_scan:      () => api.post('/wanted/refresh').then(r => r.data),
        wanted_search:    () => api.post('/wanted/search-all').then(r => r.data),
        batch_extraction: () => api.post('/wanted/batch-extract', {}).then(r => r.data),
        cleanup:          () => api.post('/tasks/cleanup/trigger').then(r => r.data),
        anidb_sync:       () => api.post('/anidb-mapping/refresh').then(r => r.data),
        bulk_auto_sync:   () => api.post('/tools/auto-sync/bulk', {}).then(r => r.data),
        cleanup_jobs:     () => api.post('/tasks/cleanup-jobs').then(r => r.data),
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

export function useCancelTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (taskName: string) => {
      const { default: api } = await import('@/api/client')
      return api.post(`/tasks/${taskName}/cancel`).then(r => r.data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
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

// ─── Phase 12: Search + Filter Presets ────────────────────────────────────

export function useGlobalSearch(query: string) {
  return useQuery({
    queryKey: ['search', query],
    queryFn: () => searchGlobal(query),
    enabled: query.trim().length >= 2,
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

/** Default page size for duplicate listing.
 *
 * The backend caps per_page at 200; we request the maximum so users with
 * larger libraries don't silently lose visibility into groups beyond the
 * first page. When total > 200 the UI surfaces a hint and users can run
 * delete on the visible batch to expose the next page on refetch.
 */
const DUPLICATES_PER_PAGE = 200

export function useDuplicates(page = 1) {
  return useQuery({
    queryKey: ['cleanup-duplicates', page, DUPLICATES_PER_PAGE],
    queryFn: () => getDuplicates(page, DUPLICATES_PER_PAGE),
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

export function useRulePreview() {
  return useMutation({
    mutationFn: (id: number) => previewCleanupRule(id),
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

// ─── ffprobe Cache ────────────────────────────────────────────────────────────

export function useFfprobeStats() {
  return useQuery({ queryKey: ['ffprobe-stats'], queryFn: getFfprobeStats })
}

export function useFfprobeCleanup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerFfprobeCleanup,
    onSuccess: (r) => {
      toast(`Removed ${r.removed} stale ffprobe cache entries`)
      void qc.invalidateQueries({ queryKey: ['ffprobe-stats'] })
    },
    onError: () => toast('Cleanup failed', 'error'),
  })
}

// ─── Database Vacuum ─────────────────────────────────────────────────────────

export function useDbVacuum() {
  return useMutation({
    mutationFn: triggerDbVacuum,
    onSuccess: (r) => toast(r.message ?? 'Database vacuumed'),
    onError: () => toast('Vacuum failed', 'error'),
  })
}

// ─── Activity Log ─────────────────────────────────────────────────────────────

export function useActivity(page = 1, perPage = 50, eventType?: string) {
  return useQuery({
    queryKey: ['activity', page, perPage, eventType],
    queryFn: () => getActivity(page, perPage, eventType),
    staleTime: 30_000,
  })
}
