import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getHealth, getStats, getJobs, getBazarrStatus,
  getBatchStatus, getConfig, updateConfig, getLibrary,
  translateFile, translateWanted, startBatch, getLogs,
} from '@/api/client'

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
    refetchInterval: 10000,
  })
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export function useJobs(page = 1, perPage = 50, status?: string) {
  return useQuery({
    queryKey: ['jobs', page, perPage, status],
    queryFn: () => getJobs(page, perPage, status),
    refetchInterval: 5000,
  })
}

// ─── Bazarr ──────────────────────────────────────────────────────────────────

export function useBazarrStatus() {
  return useQuery({
    queryKey: ['bazarr-status'],
    queryFn: getBazarrStatus,
    refetchInterval: 60000,
  })
}

// ─── Batch ───────────────────────────────────────────────────────────────────

export function useBatchStatus() {
  return useQuery({
    queryKey: ['batch-status'],
    queryFn: getBatchStatus,
    refetchInterval: 3000,
  })
}

// ─── Config ──────────────────────────────────────────────────────────────────

export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
  })
}

export function useUpdateConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => updateConfig(values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

// ─── Library ─────────────────────────────────────────────────────────────────

export function useLibrary() {
  return useQuery({
    queryKey: ['library'],
    queryFn: getLibrary,
    refetchInterval: 120000,
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

export function useTranslateWanted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (maxEpisodes?: number) => translateWanted(maxEpisodes),
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

// ─── Logs ────────────────────────────────────────────────────────────────────

export function useLogs(lines = 200, level?: string) {
  return useQuery({
    queryKey: ['logs', lines, level],
    queryFn: () => getLogs(lines, level),
    refetchInterval: 5000,
  })
}
