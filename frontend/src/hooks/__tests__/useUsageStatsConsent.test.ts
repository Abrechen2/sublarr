import { describe, it, expect, vi } from 'vitest'
import { getUsageStatsConsent, setUsageStatsConsent } from '@/api/system/usageStats'
import { api } from '@/api/core'

describe('usageStats api', () => {
  it('reads consent via the shared api client', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: { consent: 'granted' } } as never)
    const res = await getUsageStatsConsent()
    expect(res.consent).toBe('granted')
    expect(api.get).toHaveBeenCalledWith('/usage-stats/consent')
  })

  it('sets consent via POST', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ data: { consent: 'denied' } } as never)
    const res = await setUsageStatsConsent('denied')
    expect(res.consent).toBe('denied')
    expect(api.post).toHaveBeenCalledWith('/usage-stats/consent', { consent: 'denied' })
  })
})
