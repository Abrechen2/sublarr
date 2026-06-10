import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  searchGlobal, getFilterPresets, createFilterPreset, deleteFilterPreset,
  getApiKeys, updateApiKey, testApiKey, exportApiKeys, importApiKeys,
} from '@/api/client'
import type { FilterScope } from '@/lib/types'

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
