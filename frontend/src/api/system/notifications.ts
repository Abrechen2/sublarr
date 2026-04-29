import { api } from '../core'
import type {
  NotificationTemplate, NotificationHistoryEntry, QuietHoursConfig, TemplateVariable, NotificationFilter,
} from '@/lib/types'

// ─── Notification Templates ───────────────────────────────────────────────────

export async function getNotificationTemplates(): Promise<{ templates: NotificationTemplate[] }> {
  const { data } = await api.get('/notifications/templates')
  return data
}

export async function createNotificationTemplate(template: Partial<NotificationTemplate>): Promise<NotificationTemplate> {
  const { data } = await api.post('/notifications/templates', template)
  return data
}

export async function updateNotificationTemplate(id: number, template: Partial<NotificationTemplate>): Promise<NotificationTemplate> {
  const { data } = await api.put(`/notifications/templates/${id}`, template)
  return data
}

export async function deleteNotificationTemplate(id: number): Promise<void> {
  await api.delete(`/notifications/templates/${id}`)
}

export async function previewNotificationTemplate(id: number): Promise<{ title: string; body: string }> {
  const { data } = await api.post(`/notifications/templates/${id}/preview`)
  return data
}

export async function getTemplateVariables(eventType?: string): Promise<{ variables: TemplateVariable[] }> {
  const params = eventType ? { event_type: eventType } : {}
  const { data } = await api.get('/notifications/variables', { params })
  return data
}

export async function getQuietHours(): Promise<QuietHoursConfig[]> {
  // Backend returns a flat array of configs. (Earlier this client expected
  // `{ configs: [...] }` but that envelope was never produced — caused the
  // useQuietHours hook to silently return undefined for all callers.)
  const { data } = await api.get('/notifications/quiet-hours')
  return Array.isArray(data) ? data : []
}

export async function createQuietHours(config: Partial<QuietHoursConfig>): Promise<QuietHoursConfig> {
  const { data } = await api.post('/notifications/quiet-hours', config)
  return data
}

export async function updateQuietHours(id: number, config: Partial<QuietHoursConfig>): Promise<QuietHoursConfig> {
  const { data } = await api.put(`/notifications/quiet-hours/${id}`, config)
  return data
}

export async function deleteQuietHours(id: number): Promise<void> {
  await api.delete(`/notifications/quiet-hours/${id}`)
}

export async function getNotificationHistory(page = 1, eventType?: string): Promise<{
  entries: NotificationHistoryEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}> {
  const params: Record<string, unknown> = { page, per_page: 25 }
  if (eventType) params.event_type = eventType
  const { data } = await api.get('/notifications/history', { params })
  return data
}

export async function resendNotification(id: number): Promise<{ status: string }> {
  const { data } = await api.post(`/notifications/history/${id}/resend`)
  return data
}

export async function getNotificationFilters(): Promise<NotificationFilter> {
  const { data } = await api.get('/notifications/filters')
  return data
}

export async function updateNotificationFilters(filters: NotificationFilter): Promise<NotificationFilter> {
  const { data } = await api.put('/notifications/filters', filters)
  return data
}
