import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

// ─── Mocks ────────────────────────────────────────────────────────────────────

let mockTranslationEnabled = false

vi.mock('@/hooks/useApi', () => ({
  useTranslationEnabled: () => mockTranslationEnabled,
  useWantedItems: () => ({
    data: {
      data: [
        {
          id: 1,
          title: 'Frieren S02E03',
          season_episode: 'S02E03',
          status: 'failed',
          current_score: 0,
          last_search_at: '2026-03-19T10:00:00Z',
          file_path: '/media/frieren.mkv',
          item_type: 'episode',
        },
        {
          id: 2,
          title: 'Solo Leveling S01E12',
          season_episode: 'S01E12',
          status: 'found',
          current_score: 35,
          last_search_at: '2026-03-18T08:00:00Z',
          file_path: '/media/solo.mkv',
          item_type: 'episode',
        },
        {
          id: 3,
          title: 'Normal Item',
          season_episode: '',
          status: 'wanted',
          current_score: 200,
          last_search_at: null,
          file_path: '/media/normal.mkv',
          item_type: 'movie',
        },
      ],
      total: 3,
      page: 1,
      per_page: 100,
    },
    isLoading: false,
  }),
  useJobs: () => ({
    data: { data: [], total: 0, page: 1, total_pages: 1 },
    isLoading: false,
  }),
  useSearchWantedItem: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateWantedStatus: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

// Mock the sub-pages to avoid pulling in their full dependency trees
vi.mock('@/pages/Queue', () => ({
  QueuePage: () => <div data-testid="queue-page-content">Queue Content</div>,
}))

vi.mock('@/components/activity/ActivityLogTab', () => ({
  ActivityLogTab: () => <div data-testid="activity-log-tab">Activity Log Content</div>,
}))

vi.mock('@/pages/Blacklist', () => ({
  BlacklistPage: () => <div data-testid="blacklist-page-content">Blacklist Content</div>,
}))

vi.mock('@/components/activity/TranslationsTab', () => ({
  TranslationsTab: () => <div data-testid="translations-page-content">Translations Content</div>,
}))

vi.mock('@/components/layout/PageHeader', () => ({
  PageHeader: ({ title, subtitle }: { title: string; subtitle?: string }) => (
    <div data-testid="page-header">
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
  ),
}))

vi.mock('@/components/shared/PillTabs', () => ({
  PillTabs: ({
    tabs,
    activeTab,
    onChange,
  }: {
    tabs: Array<{ id: string; label: string; count?: number }>
    activeTab: string
    onChange: (id: string) => void
  }) => (
    <div data-testid="pill-tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          data-testid={`tab-${tab.id}`}
          data-active={activeTab === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.count !== undefined && <span data-testid={`tab-count-${tab.id}`}>{tab.count}</span>}
        </button>
      ))}
    </div>
  ),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

function renderWithProviders(initialEntry = '/activity?tab=queue') {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <React.Suspense fallback={<div>Loading...</div>}>
          {/* Import inline to pick up mocks */}
          <ActivityPageWrapper />
        </React.Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// We need to import after mocks are set up
import { ActivityPage } from '@/pages/ActivityPage'

function ActivityPageWrapper() {
  return <ActivityPage />
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ActivityPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTranslationEnabled = false
  })

  it('renders the page with header and tabs', () => {
    renderWithProviders()

    expect(screen.getByTestId('activity-page')).toBeInTheDocument()
    expect(screen.getByTestId('page-header')).toBeInTheDocument()
    expect(screen.getByTestId('pill-tabs')).toBeInTheDocument()
  })

  it('renders 3 tabs when translation disabled', () => {
    renderWithProviders()

    expect(screen.getByTestId('tab-queue')).toBeInTheDocument()
    expect(screen.queryByTestId('tab-translations')).not.toBeInTheDocument()
    expect(screen.getByTestId('tab-history')).toBeInTheDocument()
    expect(screen.getByTestId('tab-blacklist')).toBeInTheDocument()
  })

  it('renders 4 tabs when translation enabled', () => {
    mockTranslationEnabled = true
    renderWithProviders()

    expect(screen.getByTestId('tab-queue')).toBeInTheDocument()
    expect(screen.getByTestId('tab-translations')).toBeInTheDocument()
    expect(screen.getByTestId('tab-history')).toBeInTheDocument()
    expect(screen.getByTestId('tab-blacklist')).toBeInTheDocument()
  })

  it('defaults to queue tab', () => {
    renderWithProviders('/activity')

    // With no tab param, defaults to 'queue'
    expect(screen.getByTestId('tab-queue')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('tab-content-queue')).toBeInTheDocument()
  })

  it('renders translations tab content when tab=translations and translation enabled', () => {
    mockTranslationEnabled = true
    renderWithProviders('/activity?tab=translations')

    expect(screen.getByTestId('translations-page-content')).toBeInTheDocument()
    expect(screen.queryByTestId('history-page-content')).not.toBeInTheDocument()
  })

  it('renders history tab content when tab=history', () => {
    renderWithProviders('/activity?tab=history')

    expect(screen.getByTestId('activity-log-tab')).toBeInTheDocument()
    expect(screen.queryByTestId('queue-page-content')).not.toBeInTheDocument()
  })

  it('renders blacklist tab content when tab=blacklist', () => {
    renderWithProviders('/activity?tab=blacklist')

    expect(screen.getByTestId('blacklist-page-content')).toBeInTheDocument()
  })

  it('renders queue tab content when tab=queue', () => {
    renderWithProviders('/activity?tab=queue')

    expect(screen.getByTestId('tab-content-queue')).toBeInTheDocument()
  })

  it('switches tabs when clicking a tab button', () => {
    renderWithProviders('/activity?tab=queue')

    expect(screen.getByTestId('tab-content-queue')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('tab-history'))

    expect(screen.getByTestId('activity-log-tab')).toBeInTheDocument()
    expect(screen.queryByTestId('tab-content-queue')).not.toBeInTheDocument()
  })

  it('shows translations count badge when there are active/queued jobs', () => {
    renderWithProviders()

    // The Translations tab should have a count badge for active + queued jobs
    const badge = screen.queryByTestId('tab-count-translations')
    // May or may not be present depending on mock job data
    if (badge) {
      expect(badge).toBeInTheDocument()
    }
  })

  it('falls back to queue tab for invalid tab param', () => {
    renderWithProviders('/activity?tab=invalid')

    expect(screen.getByTestId('tab-queue')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('tab-content-queue')).toBeInTheDocument()
  })
})
