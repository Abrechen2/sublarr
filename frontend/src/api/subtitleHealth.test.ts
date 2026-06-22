import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from './core'
import { scanEpisodeHealth, fixHealthIssue, getHealthReport } from './subtitleHealth'

vi.mock('./core', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

describe('subtitleHealth api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('scanEpisodeHealth posts to the scan endpoint', async () => {
    ;(api.post as any).mockResolvedValue({
      data: { healthy: true, issues: [], issue_count: 0, episode_id: 5, video_path: '/m/x.mkv' },
    })
    const r = await scanEpisodeHealth(5)
    expect(api.post).toHaveBeenCalledWith('/library/episodes/5/health/scan')
    expect(r.healthy).toBe(true)
  })

  it('fixHealthIssue posts finding_id + action', async () => {
    ;(api.post as any).mockResolvedValue({ data: { changed: true, fix_id: 9 } })
    const r = await fixHealthIssue(5, 7, 'repair_escapes')
    expect(api.post).toHaveBeenCalledWith('/library/episodes/5/health/fix', {
      finding_id: 7,
      action: 'repair_escapes',
      opts: undefined,
    })
    expect(r.fix_id).toBe(9)
  })

  it('getHealthReport gets the report', async () => {
    ;(api.get as any).mockResolvedValue({
      data: { total_findings: 3, by_type: {}, affected_episodes: 1 },
    })
    const r = await getHealthReport()
    expect(api.get).toHaveBeenCalledWith('/subtitle-health/report')
    expect(r.total_findings).toBe(3)
  })
})
