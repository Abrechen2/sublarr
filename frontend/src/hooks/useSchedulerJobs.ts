import { useQuery } from '@tanstack/react-query'
import { getJob, listJobs } from '@/api/scheduler'

// ─── Scheduler Jobs — Phase 5 Rollout 2 ──────────────────────────────────────

export function useSchedulerJobs(refetchMs = 10000) {
  return useQuery({
    queryKey: ['scheduler', 'jobs'],
    queryFn: listJobs,
    refetchInterval: refetchMs,
    refetchOnWindowFocus: false,
  })
}

export function useSchedulerJob(id: string, enabled = true) {
  return useQuery({
    queryKey: ['scheduler', 'jobs', id],
    queryFn: () => getJob(id),
    enabled,
    refetchInterval: 10000,
  })
}
