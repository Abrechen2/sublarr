import { useQuery } from '@tanstack/react-query'
import { listRuns } from '@/api/scheduler'

// ─── Scheduler Job Runs — Phase 5 Rollout 2 ──────────────────────────────────

export function useSchedulerJobRuns(
  id: string,
  params: { limit?: number; offset?: number; status?: string } = {},
  enabled = true,
) {
  return useQuery({
    queryKey: ['scheduler', 'jobs', id, 'runs', params],
    queryFn: () => listRuns(id, params),
    enabled,
    refetchInterval: 5000,
  })
}
