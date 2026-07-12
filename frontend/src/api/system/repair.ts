/** Repair of subtitles damaged by the pre-1.6.6 processing pipeline. */
import { api } from '@/api/core'

export interface RepairScan {
  damaged: number
  untouched: number
  missing_from_disk: number
  unresolvable: number
  already_repaired: number
  recoverable_from_backup: number
  needs_download: number
  needs_download_by_provider: Record<string, number>
}

export interface RepairStatus {
  running: boolean
  dry_run: boolean
  language: string | null
  total: number
  done: number
  repaired: number
  from_bak: number
  from_provider: number
  skipped_unprovable: number
  skipped_nothing_to_restore: number
  failed: number
  quota_exhausted: boolean
  resume_at: string | null
  last_file: string
  error: string
  recent: { file: string; status: string }[]
}

export async function scanDamaged(language?: string): Promise<RepairScan> {
  const { data } = await api.get('/repair/scan', { params: language ? { language } : {} })
  return data
}

export async function startRepair(opts: {
  language?: string
  dry_run?: boolean
  limit?: number
}): Promise<void> {
  await api.post('/repair/run', opts)
}

export async function getRepairStatus(): Promise<RepairStatus> {
  const { data } = await api.get('/repair/status')
  return data
}
