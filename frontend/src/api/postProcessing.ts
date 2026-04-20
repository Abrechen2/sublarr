import { api } from './core'

// Plan B6 — post-processing pipeline API client

export interface PostProcessingOp {
  op_id: string
  label: string
  description: string
}

export interface PostProcessingConfig {
  after_download: string[]
  after_translate: string[]
  after_sync: string[]
}

export type Trigger = keyof PostProcessingConfig

export interface PostProcessingRun {
  id: number
  trigger: string
  ops_executed: Record<string, unknown>
  duration_ms: number
  outcome: string
  created_at: string | null
}

export async function fetchOps(): Promise<PostProcessingOp[]> {
  const { data } = await api.get<{ ops: PostProcessingOp[] }>('/post-processing/ops')
  return data.ops
}

export async function fetchConfig(): Promise<PostProcessingConfig> {
  const { data } = await api.get<PostProcessingConfig>('/post-processing/config')
  return data
}

export async function updateTrigger(trigger: Trigger, op_ids: string[]): Promise<void> {
  await api.put(`/post-processing/config/${trigger}`, { op_ids })
}

export async function fetchRuns(limit = 50): Promise<PostProcessingRun[]> {
  const { data } = await api.get<{ runs: PostProcessingRun[] }>(
    `/post-processing/runs?limit=${limit}`,
  )
  return data.runs
}

// --- Per-op config (B6 follow-up) -----------------------------------------

export type OpConfigFieldType = 'text' | 'password' | 'number'

export interface OpConfigSchemaEntry {
  key: string
  label: string
  type: OpConfigFieldType
  required: boolean
  default: string
}

export interface OpConfigResponse {
  op_id: string
  schema: OpConfigSchemaEntry[]
  values: Record<string, string>
}

export async function fetchOpConfig(opId: string): Promise<OpConfigResponse> {
  const { data } = await api.get<OpConfigResponse>(
    `/post-processing/ops/${opId}/config`,
  )
  return data
}

export async function updateOpConfig(
  opId: string,
  values: Record<string, string>,
): Promise<void> {
  await api.put(`/post-processing/ops/${opId}/config`, { values })
}
