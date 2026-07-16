import { useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSetupStatus, completeSetup, type SetupProfile } from '@/api/health'
import {
  getBudgetState,
  getHealth, getUpdateInfo, getStats, getJobs,
  getBatchStatus, getConfig, updateConfig, disableTranslation,
  getLogs,
  retryJob, cancelQueuedJob, clearQueuedJobs,
  exportConfig, importConfig,
  getSupportedLanguages,
  testSonarrInstance, testRadarrInstance,
} from '@/api/client'

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

/**
 * Debounced autosave for settings pages.
 *
 * Each patch is written to the ['config'] cache immediately (optimistic echo,
 * so controlled inputs reflect the keystroke without waiting for the network),
 * then the real PUT is debounced per key so rapid edits to one field collapse
 * into a single request. Every PUT triggers a full backend config reconcile,
 * so the previous per-keystroke, non-debounced saves were the driver behind
 * the ~12s settings-lag reports. Different keys still save independently.
 */
export function useDebouncedConfigSave(delayMs = 400) {
  const queryClient = useQueryClient()
  const { mutate } = useUpdateConfig()
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    const map = timers.current
    return () => {
      map.forEach((timer) => clearTimeout(timer))
      map.clear()
    }
  }, [])

  return useCallback(
    (patch: Record<string, unknown>) => {
      // Instant optimistic echo so the input never freezes on the stale value.
      queryClient.setQueryData<Record<string, unknown>>(['config'], (old) => ({
        ...(old ?? {}),
        ...patch,
      }))
      for (const [key, value] of Object.entries(patch)) {
        const existing = timers.current.get(key)
        if (existing) clearTimeout(existing)
        timers.current.set(
          key,
          setTimeout(() => {
            timers.current.delete(key)
            mutate({ [key]: value })
          }, delayMs),
        )
      }
    },
    [queryClient, mutate, delayMs],
  )
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

/** Mutation: cancels a queued job (or deletes a finished one from history). */
export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => cancelQueuedJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

/** Mutation: cancels all queued translation jobs. */
export function useClearQueuedJobs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => clearQueuedJobs(),
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
