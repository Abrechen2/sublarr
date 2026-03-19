import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  getWantedItems, getWantedSummary, refreshWanted,
  updateWantedItemStatus,
  searchWantedItem, processWantedItem, extractEmbeddedSub,
  startWantedBatchSearch, getWantedBatchStatus, getBatchExtractStatus, getBatchProbeStatus, startBatchProbe,
  searchAllWanted,
  getScannerStatus,
  cleanupSidecars,
} from '@/api/client'

// ─── Wanted ─────────────────────────────────────────────────────────────

/** When fetchAll=true, fetches page=1 with perPage=9999 (cap ~9999 items). Sufficient for typical Wanted lists. */
export function useWantedItems(page = 1, perPage = 50, itemType?: string, status?: string, subtitleType?: string, fetchAll = false) {
  return useQuery({
    queryKey: ['wanted', fetchAll ? 'all' : page, fetchAll ? 9999 : perPage, itemType, status, subtitleType],
    queryFn: () =>
      getWantedItems(
        fetchAll ? 1 : page,
        fetchAll ? 9999 : perPage,
        itemType,
        status,
        subtitleType,
      ),
    placeholderData: keepPreviousData,
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

export function useWantedBatchExtractStatus() {
  return useQuery({
    queryKey: ['wanted-batch-extract-status'],
    queryFn: getBatchExtractStatus,
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  })
}

export function useWantedBatchProbeStatus() {
  return useQuery({
    queryKey: ['wanted-batch-probe-status'],
    queryFn: getBatchProbeStatus,
    refetchInterval: (query) => (query.state.data?.running ? 2000 : false),
  })
}

export function useScannerStatus() {
  return useQuery({
    queryKey: ['scanner-status'],
    queryFn: getScannerStatus,
    refetchInterval: (query) =>
      query.state.data?.is_scanning || query.state.data?.is_searching ? 3000 : 30000,
  })
}

export function useStartBatchProbe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (seriesId?: number) => startBatchProbe(seriesId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted-batch-probe-status'] })
    },
  })
}

export function useCleanupSidecars() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars?: { itemIds?: number[]; dryRun?: boolean }) =>
      cleanupSidecars(vars?.itemIds, vars?.dryRun),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
      queryClient.invalidateQueries({ queryKey: ['wanted-summary'] })
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
