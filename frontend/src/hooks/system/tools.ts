import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from '@/components/shared/Toast'
import {
  getFfprobeStats, triggerFfprobeCleanup, triggerDbVacuum,
  getActivity,
} from '@/api/client'

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
