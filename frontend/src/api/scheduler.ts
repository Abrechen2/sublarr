import { api } from './core'
import type { SchedulerJob, SchedulerJobRun, Trigger } from '@/lib/types'

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

export async function runNow(id: string): Promise<{ status: string; oneshot_id: string }> {
  const { data } = await api.post(`/scheduler/jobs/${encodeURIComponent(id)}/run-now`)
  return data
}

export async function pauseJob(id: string): Promise<{ status: string }> {
  const { data } = await api.post(`/scheduler/jobs/${encodeURIComponent(id)}/pause`)
  return data
}

export async function resumeJob(id: string): Promise<{ status: string }> {
  const { data } = await api.post(`/scheduler/jobs/${encodeURIComponent(id)}/resume`)
  return data
}

export async function modifyTrigger(id: string, trigger: Trigger): Promise<SchedulerJob> {
  const { data } = await api.patch(
    `/scheduler/jobs/${encodeURIComponent(id)}`,
    { trigger },
  )
  return data
}

export async function resetDefault(id: string): Promise<SchedulerJob> {
  const { data } = await api.post(
    `/scheduler/jobs/${encodeURIComponent(id)}/reset-default`,
  )
  return data
}
