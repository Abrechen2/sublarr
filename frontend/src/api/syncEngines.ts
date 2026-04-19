import { api } from './core'

// Plan B7 — multi-engine sync orchestrator API client.

export interface SyncEngineInfo {
  name: string
  available: boolean
  timeout_s: number
}

export interface SyncEnginesResponse {
  engines: SyncEngineInfo[]
  sanity_threshold_ms: number
}

export interface SyncJobRun {
  id: number
  engine: string
  status: string
  offset_ms: number | null
  duration_ms: number
  subtitle_path: string | null
  video_path: string | null
  reason: string | null
  created_at: string | null
}

export async function fetchSyncEngines(): Promise<SyncEnginesResponse> {
  const { data } = await api.get<SyncEnginesResponse>('/sync/engines')
  return data
}

export async function fetchSyncRuns(limit = 50): Promise<SyncJobRun[]> {
  const { data } = await api.get<{ runs: SyncJobRun[] }>(`/sync/runs?limit=${limit}`)
  return data.runs
}
