import { api } from '../core'
import type {
  WatchedFolder, StandaloneSeries, StandaloneMovie, StandaloneStatus,
  StatisticsData, FullBackupInfo,
} from '@/lib/types'

// ─── Standalone Mode ──────────────────────────────────────────────────────────

export async function getWatchedFolders(): Promise<WatchedFolder[]> {
  const { data } = await api.get('/standalone/folders')
  return data
}

export async function saveWatchedFolder(folder: Partial<WatchedFolder> & { path: string }): Promise<WatchedFolder> {
  if (folder.id) {
    const { data } = await api.put(`/standalone/folders/${folder.id}`, folder)
    return data
  }
  const { data } = await api.post('/standalone/folders', folder)
  return data
}

export async function deleteWatchedFolder(folderId: number): Promise<void> {
  await api.delete(`/standalone/folders/${folderId}`)
}

export async function getStandaloneSeries(): Promise<StandaloneSeries[]> {
  const { data } = await api.get('/standalone/series')
  return data
}

export async function getStandaloneMovies(): Promise<StandaloneMovie[]> {
  const { data } = await api.get('/standalone/movies')
  return data
}

export async function triggerStandaloneScan(): Promise<{ message: string }> {
  const { data } = await api.post('/standalone/scan')
  return data
}

export async function triggerStandaloneFolderScan(folderId: number): Promise<{ message: string }> {
  const { data } = await api.post(`/standalone/scan/${folderId}`)
  return data
}

export async function getStandaloneStatus(): Promise<StandaloneStatus> {
  const { data } = await api.get('/standalone/status')
  return data
}

export async function rescanSeries(seriesId: number): Promise<{ message: string; series_id: number }> {
  const { data } = await api.post(`/standalone/series/${seriesId}/scan`)
  return data
}

export async function refreshSeriesMetadata(seriesId: number): Promise<void> {
  await api.post(`/standalone/series/${seriesId}/refresh-metadata`)
}

// ─── Statistics ──────────────────────────────────────────────────────────────

export async function getStatistics(range: string): Promise<StatisticsData> {
  const { data } = await api.get('/statistics', { params: { range } })
  return data
}

export async function exportStatistics(range: string, format: 'json' | 'csv'): Promise<Blob> {
  const { data } = await api.get('/statistics/export', {
    params: { range, format },
    responseType: 'blob',
  })
  return data
}

// ─── Full Backup ─────────────────────────────────────────────────────────────

export async function createFullBackup(): Promise<FullBackupInfo> {
  const { data } = await api.post('/backup/full')
  return data
}

export async function listFullBackups(): Promise<{ backups: FullBackupInfo[] }> {
  const { data } = await api.get('/backup/full/list')
  return data
}

export function downloadFullBackupUrl(filename: string): string {
  return `/api/v1/backup/full/download/${filename}`
}

export async function restoreFullBackup(file: File): Promise<{ status: string; config_imported: string[]; db_restored: boolean }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/backup/full/restore', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
