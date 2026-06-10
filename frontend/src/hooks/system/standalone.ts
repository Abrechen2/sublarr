import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWatchedFolders, saveWatchedFolder, deleteWatchedFolder,
  getStandaloneSeries, getStandaloneMovies, triggerStandaloneScan, triggerStandaloneFolderScan,
  getStandaloneStatus, refreshSeriesMetadata,
} from '@/api/client'

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
