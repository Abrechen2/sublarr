import { api } from './core'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SidecarBatch {
  batch_id: string
  created_at: string | null
  expires_at: string | null
  file_count: number
  size_bytes: number
  series_name: string
  language: string
  files: string[]
}

export interface MkvBackup {
  path: string
  video_path: string | null
  size_bytes: number
  mtime: number
  expires_at: string | null
}

export interface TrashOverview {
  sidecar_batches: SidecarBatch[]
  mkv_backups: MkvBackup[]
  total_size_bytes: number
  retention: {
    subtitle_trash_days: number
    mkv_backup_days: number
  }
}

export interface RestoreResult {
  restored: string
  backup_removed: string
  sidecars_deleted: number
}

// ─── API calls ────────────────────────────────────────────────────────────────

export async function getTrashOverview(): Promise<TrashOverview> {
  const { data } = await api.get('/trash')
  return data
}

export async function restoreSidecarBatch(batchId: string): Promise<{ restored: number; failed: number }> {
  const { data } = await api.post(`/library/trash/${batchId}/restore`)
  return data
}

export async function deleteSidecarBatch(batchId: string): Promise<{ deleted: number }> {
  const { data } = await api.delete(`/library/trash/${batchId}`)
  return data
}

export async function restoreMkvBackup(
  backupPath: string,
  videoPath: string,
  deleteSidecars = false,
): Promise<RestoreResult> {
  const { data } = await api.post('/remux/backups/restore', {
    backup_path: backupPath,
    video_path: videoPath,
    delete_sidecars: deleteSidecars,
  })
  return data
}
