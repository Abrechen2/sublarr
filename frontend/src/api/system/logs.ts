import { api } from '../core'
import type { LogRotationConfig, SupportPreview } from '@/lib/types'

// ─── Notifications (test / status) ───────────────────────────────────────────

export async function testNotification(url?: string): Promise<{ success: boolean; message: string }> {
  const body = url ? { url } : {}
  const { data } = await api.post('/notifications/test', body)
  return data
}

export async function getNotificationStatus(): Promise<{
  configured: boolean
  url_count: number
  events: Record<string, boolean>
}> {
  const { data } = await api.get('/notifications/status')
  return data
}

// ─── Logs ────────────────────────────────────────────────────────────────────

export async function getLogs(lines = 200, level?: string) {
  const params: Record<string, unknown> = { lines }
  if (level) params.level = level
  const { data } = await api.get('/logs', { params })
  return data
}

// ─── Log Rotation ────────────────────────────────────────────────────────────

export async function getLogRotation(): Promise<LogRotationConfig> {
  const { data } = await api.get('/logs/rotation')
  return data
}

/** `live` is false when the backend saved the values but could not re-apply
 *  them to the running handler (they then take effect on restart). */
export interface LogRotationUpdateResult extends LogRotationConfig {
  status?: 'applied' | 'saved'
  live?: boolean
  note?: string
}

export async function updateLogRotation(
  config: LogRotationConfig,
): Promise<LogRotationUpdateResult> {
  const { data } = await api.put('/logs/rotation', config)
  return data
}

// ─── Support Export ───────────────────────────────────────────────────────────

export async function fetchSupportPreview(): Promise<SupportPreview> {
  const res = await api.get<SupportPreview>('/logs/support-preview')
  return res.data
}

export async function downloadSupportBundle(): Promise<void> {
  const res = await api.get('/logs/support-export', { responseType: 'blob' })
  const contentDisposition = res.headers['content-disposition'] as string | undefined
  const filenameMatch = contentDisposition?.match(/filename="?([^"]+)"?/)
  const filename =
    filenameMatch?.[1] ??
    `sublarr-support-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
