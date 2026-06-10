import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getStatistics, exportStatistics,
  createFullBackup, listFullBackups, restoreFullBackup,
  getLogRotation, updateLogRotation,
  getTasks,
  runHealthCheck, applyHealthFix, getQualityTrends,
} from '@/api/client'
import type { LogRotationConfig } from '@/lib/types'

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
