import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  getCleanupStats, startCleanupScan, getCleanupScanStatus,
  getDuplicates, deleteDuplicates,
  scanOrphaned, getOrphanedFiles, deleteOrphaned,
  getCleanupRules, createCleanupRule, updateCleanupRule, deleteCleanupRule, runCleanupRule, previewCleanupRule,
  getCleanupHistory, getCleanupPreview,
} from '@/api/client'
import type { CleanupRule } from '@/lib/types'

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
