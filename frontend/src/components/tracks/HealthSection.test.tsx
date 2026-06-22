import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { HealthSection } from './HealthSection'
import * as api from '@/api/subtitleHealth'

vi.mock('@/api/subtitleHealth')
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: any) => (o?.count != null ? `${o.count} ${k}` : k),
  }),
}))

describe('HealthSection', () => {
  beforeEach(() => vi.clearAllMocks())

  it('scans and renders issues', async () => {
    vi.mocked(api.scanEpisodeHealth).mockResolvedValue({
      episode_id: 5,
      video_path: '/m/x.mkv',
      healthy: false,
      issue_count: 1,
      issues: [
        {
          id: 1,
          type: 'ass_escape_leak',
          severity: 'confirmed',
          episode_id: 5,
          target_kind: 'sidecar',
          target_path: '/m/x.de.srt',
          stream_index: null,
          lang: 'de',
          count: 3,
          snippets: ['erkannt\\Nwie'],
          raw_hash: 'h',
          fixable: true,
          suggested_fix: 'repair_escapes',
        },
      ],
    })
    render(<HealthSection episodeId={5} />)
    fireEvent.click(screen.getByText('subtitle_health.scan'))
    await waitFor(() =>
      expect(screen.getByText('subtitle_health.types.ass_escape_leak')).toBeInTheDocument(),
    )
  })

  it('hides shadowed findings (clean sidecar covers the embedded defect)', async () => {
    vi.mocked(api.scanEpisodeHealth).mockResolvedValue({
      episode_id: 5,
      video_path: '/m/x.mkv',
      healthy: false,
      issue_count: 1,
      issues: [
        {
          id: 1,
          shadowed: true,
          type: 'ass_escape_leak',
          severity: 'confirmed',
          episode_id: 5,
          target_kind: 'embedded',
          target_path: '/m/x.mkv',
          stream_index: 0,
          lang: 'ger',
          count: 198,
          snippets: [],
          raw_hash: 'h',
          fixable: true,
          suggested_fix: 'extract_clean_sidecar',
        },
      ],
    })
    render(<HealthSection episodeId={5} />)
    fireEvent.click(screen.getByText('subtitle_health.scan'))
    await waitFor(() => expect(screen.getByText('subtitle_health.healthy')).toBeInTheDocument())
    expect(screen.queryByText('subtitle_health.types.ass_escape_leak')).not.toBeInTheDocument()
  })

  it('applies a fix and marks it resolved', async () => {
    vi.mocked(api.scanEpisodeHealth).mockResolvedValue({
      episode_id: 5,
      video_path: '/m/x.mkv',
      healthy: false,
      issue_count: 1,
      issues: [
        {
          id: 1,
          type: 'ass_escape_leak',
          severity: 'confirmed',
          episode_id: 5,
          target_kind: 'sidecar',
          target_path: '/m/x.de.srt',
          stream_index: null,
          lang: 'de',
          count: 3,
          snippets: [],
          raw_hash: 'h',
          fixable: true,
          suggested_fix: 'repair_escapes',
        },
      ],
    })
    vi.mocked(api.fixHealthIssue).mockResolvedValue({ changed: true, fix_id: 9 })
    render(<HealthSection episodeId={5} />)
    fireEvent.click(screen.getByText('subtitle_health.scan'))
    await waitFor(() => screen.getByText('subtitle_health.fix'))
    fireEvent.click(screen.getByText('subtitle_health.fix'))
    await waitFor(() =>
      expect(api.fixHealthIssue).toHaveBeenCalledWith(5, 1, 'repair_escapes'),
    )
  })
})
