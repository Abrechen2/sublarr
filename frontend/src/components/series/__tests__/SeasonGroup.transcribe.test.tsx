import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockTranscribeMutate = vi.fn()
const mockDetectMutate = vi.fn()

vi.mock('@/hooks/useTranslationApi', () => ({
  useTranscribeEpisode: () => ({ mutate: mockTranscribeMutate, isPending: false }),
  useDetectOpeningEnding: () => ({ mutate: mockDetectMutate, isPending: false }),
  useBatchTranslate: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/components/library/EpisodeRow', () => ({
  getRowStatus: () => 'ok',
}))

vi.mock('./EpisodeSearchPanel', () => ({
  EpisodeSearchPanel: () => null,
}))

vi.mock('./EpisodeHistoryPanel', () => ({
  EpisodeHistoryPanel: () => null,
}))

vi.mock('@/components/tracks/TrackPanel', () => ({
  TrackPanel: () => null,
}))

vi.mock('./EpisodeGrid', () => ({
  EPISODE_GRID_COLUMNS: '28px 50px 1fr 90px minmax(180px,1.5fr) 170px',
}))

vi.mock('./seriesUtils', () => ({
  deriveSubtitlePath: () => null,
  normLang: (code: string) => code,
}))

vi.mock('@/components/health/HealthBadge', () => ({
  HealthBadge: () => null,
}))

vi.mock('@/components/episodes/EpisodeActionMenu', () => ({
  EpisodeActionMenu: () => null,
}))

vi.mock('@/components/processing/SubtitleActionsMenu', () => ({
  SubtitleActionsMenu: () => null,
}))

vi.mock('@/api/client', () => ({
  startWantedBatchSearch: vi.fn(),
  exportSubtitleNfo: vi.fn(),
  getSubtitleDownloadUrl: vi.fn(() => ''),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

// ─── Test Data ────────────────────────────────────────────────────────────────

const baseEpisode = {
  id: 101,
  title: 'Test Episode',
  episode: 1,
  season: 1,
  has_file: true,
  file_path: '/media/show/s01e01.mkv',
  subtitles: {},
  subtitle_scores: {},
  subtitle_providers: {},
  wanted_status: null,
  wanted_id: null,
}

const baseProps = {
  season: 1,
  episodes: [baseEpisode],
  targetLanguages: ['de'],
  seriesId: 1,
  isExtracting: false,
  onExtract: vi.fn(),
  expandedEp: null,
  onSearch: vi.fn(),
  onInteractiveSearch: vi.fn(),
  onHistory: vi.fn(),
  onTracks: vi.fn(),
  onClose: vi.fn(),
  searchResults: null,
  searchLoading: false,
  historyEntries: [],
  historyLoading: false,
  onProcess: vi.fn(),
  onPreviewSub: vi.fn(),
  onEditSub: vi.fn(),
  onCompare: vi.fn(),
  onCombine: vi.fn(),
  onSync: vi.fn(),
  onSyncCompare: vi.fn(),
  onAutoSync: vi.fn(),
  onVideoSync: vi.fn(),
  onHealthCheck: vi.fn(),
  healthScores: {},
  onOpenEditor: vi.fn(),
  sidecarMap: {},
  onDeleteSidecar: vi.fn(),
  onOpenCleanupModal: vi.fn(),
  onPreview: vi.fn(),
  streamingEnabled: false,
  onRefreshSidecars: vi.fn(),
  t: (key: string) => key,
}

// ─── Tests ───────────────────────────────────────────────────────────────────

import { SeasonGroup } from '../SeasonGroup'

describe('SeasonGroup transcribe and detect buttons (Steps 62 & 63)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders transcribe button for episode with file', () => {
    render(<SeasonGroup {...baseProps} />)
    expect(screen.getByTestId('transcribe-btn-101')).toBeTruthy()
  })

  it('renders detect-oped button for episode with file', () => {
    render(<SeasonGroup {...baseProps} />)
    expect(screen.getByTestId('detect-oped-btn-101')).toBeTruthy()
  })

  it('calls transcribe.mutate with correct filePath on click', () => {
    render(<SeasonGroup {...baseProps} />)
    fireEvent.click(screen.getByTestId('transcribe-btn-101'))
    expect(mockTranscribeMutate).toHaveBeenCalledWith({ filePath: '/media/show/s01e01.mkv' })
  })

  it('calls detectOpEd.mutate with correct filePath on click', () => {
    render(<SeasonGroup {...baseProps} />)
    fireEvent.click(screen.getByTestId('detect-oped-btn-101'))
    expect(mockDetectMutate).toHaveBeenCalledWith('/media/show/s01e01.mkv')
  })

  it('does not render transcribe/detect buttons when episode has no file', () => {
    const noFileEpisode = { ...baseEpisode, has_file: false, file_path: '' }
    render(<SeasonGroup {...baseProps} episodes={[noFileEpisode]} />)
    expect(screen.queryByTestId('transcribe-btn-101')).toBeNull()
    expect(screen.queryByTestId('detect-oped-btn-101')).toBeNull()
  })
})
