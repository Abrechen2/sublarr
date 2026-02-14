import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getHealth, getStats, getJobs,
  getBatchStatus, getConfig, updateConfig, getLibrary,
  translateFile, startBatch, getLogs,
  getWantedItems, getWantedSummary, refreshWanted,
  updateWantedItemStatus, deleteWantedItem,
  searchWantedItem, processWantedItem,
  startWantedBatchSearch, getWantedBatchStatus,
  getProviders, testProvider, getProviderStats, clearProviderCache,
  searchAllWanted, getRetranslateStatus, retranslateSingle, retranslateBatch,
  getLanguageProfiles, createLanguageProfile, updateLanguageProfile,
  deleteLanguageProfile, assignProfile,
} from '@/api/client'
import type { LanguageProfile } from '@/lib/types'

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

// ─── Batch ───────────────────────────────────────────────────────────────────

export function useBatchStatus() {
  return useQuery({
    queryKey: ['batch-status'],
    queryFn: getBatchStatus,
    refetchInterval: 5000,
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

// ─── Wanted ─────────────────────────────────────────────────────────────

export function useWantedItems(page = 1, perPage = 50, itemType?: string, status?: string) {
  return useQuery({
    queryKey: ['wanted', page, perPage, itemType, status],
    queryFn: () => getWantedItems(page, perPage, itemType, status),
    refetchInterval: 30000,
  })
}

export function useWantedSummary() {
  return useQuery({
    queryKey: ['wanted-summary'],
    queryFn: getWantedSummary,
    refetchInterval: 30000,
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

export function useStartWantedBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (itemIds?: number[]) => startWantedBatchSearch(itemIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted-batch-status'] })
    },
  })
}

export function useWantedBatchStatus() {
  return useQuery({
    queryKey: ['wanted-batch-status'],
    queryFn: getWantedBatchStatus,
    refetchInterval: 3000,
  })
}

// ─── Providers ───────────────────────────────────────────────────────────────

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: getProviders,
    refetchInterval: 30000,
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
    refetchInterval: 30000,
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
    refetchInterval: 60000,
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
    refetchInterval: 10000,
  })
}
