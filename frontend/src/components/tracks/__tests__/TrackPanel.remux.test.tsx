import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mocks = vi.hoisted(() => ({
  removeTrack: vi.fn().mockResolvedValue({ job_id: 'test-job-123', status: 'pending' }),
}))

vi.mock('@/api/client', () => ({
  listEpisodeTracks: vi.fn().mockResolvedValue({
    video_path: '/media/show/s01e01.mkv',
    tracks: [
      {
        index: 2,
        codec: 'ass',
        codec_type: 'subtitle',
        language: 'de',
        title: 'German',
        default: false,
        forced: false,
      },
    ],
  }),
  extractTrack: vi.fn(),
  convertSubtitle: vi.fn(),
  removeTrackFromContainer: mocks.removeTrack,
  getRemuxJob: vi.fn().mockResolvedValue({ job_id: 'test-job-123', status: 'pending', result: null, error: null }),
  restoreRemuxBackup: vi.fn(),
  detectDubtitle: vi.fn(),
  getCachedDubtitle: vi.fn().mockResolvedValue(null),
  listEpisodeSubtitles: vi.fn().mockResolvedValue({ subtitles: [], video_path: '/media/show/s01e01.mkv' }),
  deleteSubtitles: vi.fn(),
  subtitleDownloadUrl: (p: string) => `/dl?path=${p}`,
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Tests ───────────────────────────────────────────────────────────────────

import { TrackPanel } from '../TrackPanel'

describe('TrackPanel remux remove button (Step 66)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders remux-remove-track button for subtitle track', async () => {
    render(<TrackPanel episodeId={1} onOpenEditor={vi.fn()} />)
    // Wait for async track load
    const btn = await screen.findByTestId('remux-remove-track-2')
    expect(btn).toBeTruthy()
  })

  it('shows confirm state on first click', async () => {
    render(<TrackPanel episodeId={1} onOpenEditor={vi.fn()} />)
    const btn = await screen.findByTestId('remux-remove-track-2')
    fireEvent.click(btn)
    // After first click, button shows confirm text
    expect(btn.textContent).toContain('Sure?')
  })

  it('calls removeTrackFromContainer on second click', async () => {
    render(<TrackPanel episodeId={1} onOpenEditor={vi.fn()} />)
    const btn = await screen.findByTestId('remux-remove-track-2')
    // First click: enter confirm state
    fireEvent.click(btn)
    // Second click: actual removal
    fireEvent.click(btn)
    expect(mocks.removeTrack).toHaveBeenCalledWith(1, 2)
  })
})
