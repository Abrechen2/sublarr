import { api } from './core'
import type { EpisodeHealthResult, HealthFixResult, HealthReport } from '@/lib/types'

export async function scanEpisodeHealth(epId: number): Promise<EpisodeHealthResult> {
  const { data } = await api.post(`/library/episodes/${epId}/health/scan`)
  return data
}

export async function scanSeriesHealth(
  seriesId: number,
): Promise<{ status: string; series_id: number }> {
  const { data } = await api.post(`/library/series/${seriesId}/health/scan`)
  return data
}

export async function fixHealthIssue(
  epId: number,
  findingId: number,
  action: string,
  opts?: Record<string, unknown>,
): Promise<HealthFixResult> {
  const { data } = await api.post(`/library/episodes/${epId}/health/fix`, {
    finding_id: findingId,
    action,
    opts,
  })
  return data
}

export async function rollbackHealthFix(
  fixId: number,
): Promise<{ restored: boolean; reason?: string }> {
  const { data } = await api.post(`/subtitle-health/fixes/${fixId}/rollback`)
  return data
}

export async function dismissHealthFinding(findingId: number): Promise<{ dismissed: boolean }> {
  const { data } = await api.post(`/subtitle-health/findings/${findingId}/dismiss`)
  return data
}

export async function getHealthReport(): Promise<HealthReport> {
  const { data } = await api.get('/subtitle-health/report')
  return data
}
