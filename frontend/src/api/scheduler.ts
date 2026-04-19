import { api } from './core'
import type { SchedulerJob, SchedulerJobRun } from '@/lib/types'

// ─── Scheduler — Phase 5 Rollout 2 ───────────────────────────────────────────

export async function listJobs(): Promise<{ jobs: SchedulerJob[] }> {
  const { data } = await api.get('/scheduler/jobs')
  return data
}

export async function getJob(id: string): Promise<SchedulerJob> {
  const { data } = await api.get(`/scheduler/jobs/${encodeURIComponent(id)}`)
  return data
}

export async function listRuns(
  id: string,
  params?: { limit?: number; offset?: number; status?: string },
): Promise<{ total: number; limit: number; offset: number; runs: SchedulerJobRun[] }> {
  const search = new URLSearchParams()
  if (params?.limit) search.set('limit', String(params.limit))
  if (params?.offset) search.set('offset', String(params.offset))
  if (params?.status) search.set('status', params.status)
  const qs = search.toString()
  const { data } = await api.get(
    `/scheduler/jobs/${encodeURIComponent(id)}/runs${qs ? `?${qs}` : ''}`,
  )
  return data
}
