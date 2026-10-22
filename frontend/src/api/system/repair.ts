/** Repair of subtitles damaged by the pre-1.6.6 processing pipeline. */
import { api } from '@/api/core'

export interface RepairScan {
  damaged: number
  untouched: number
  missing_from_disk: number
  unresolvable: number
  /** Quarantined as another episode's subtitle — replaced, never repaired. */
  quarantined: number
  already_repaired: number
  /** Repaired as far as provable; edited lines still carry "�". */
  partially_repaired: number
  partially_repaired_files: string[]
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
  partial: number
  from_bak: number
  from_provider: number
  skipped_unprovable: number
  skipped_nothing_to_restore: number
  failed: number
  /** Needed a download this pass did not make (backups only, or quota spent). */
  deferred: number
  local_only: boolean
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
  local_only?: boolean
  limit?: number
}): Promise<void> {
  await api.post('/repair/run', opts)
}

export async function getRepairStatus(): Promise<RepairStatus> {
  const { data } = await api.get('/repair/status')
  return data
}

/** A saved subtitle whose winning release names another episode than its video. */
export interface WrongEpisodeFinding {
  video: string
  sidecar: string
  language: string
  provider: string
  subtitle_id: string
  release: string
  reason: string
}

export async function scanWrongEpisodes(
  language?: string,
): Promise<{ count: number; findings: WrongEpisodeFinding[] }> {
  const { data } = await api.get('/repair/wrong-episodes', {
    params: language ? { language } : {},
  })
  return data
}

export async function requeueWrongEpisodes(language?: string): Promise<void> {
  await api.post('/repair/wrong-episodes/requeue', language ? { language } : {})
}
