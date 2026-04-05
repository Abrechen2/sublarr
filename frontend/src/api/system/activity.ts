import { api } from '../core'

export interface ActivityEntry {
  id: number
  event_type: 'download' | 'extract' | 'delete' | 'scan'
  file_path: string | null
  status: 'success' | 'failed'
  details: Record<string, unknown> | null
  created_at: string
}

export interface PaginatedActivity {
  data: ActivityEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export async function getActivity(
  page = 1,
  perPage = 50,
  eventType?: string,
): Promise<PaginatedActivity> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (eventType) params.type = eventType
  const { data } = await api.get('/activity', { params })
  return data
}
