import { api } from '@/api/core'

export type Consent = 'unset' | 'granted' | 'denied'

export async function getUsageStatsConsent(): Promise<{ consent: Consent }> {
  const { data } = await api.get('/usage-stats/consent')
  return data
}

export async function setUsageStatsConsent(
  consent: 'granted' | 'denied',
): Promise<{ consent: Consent }> {
  const { data } = await api.post('/usage-stats/consent', { consent })
  return data
}
