import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'
import { DashboardSidebar } from '../DashboardSidebar'

const mockRefresh = vi.fn()
const mockBatch = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useProviders: () => ({
    data: {
      providers: [
        { name: 'OpenSubtitles', enabled: true, healthy: true, stats: { success_rate: 0.97 } },
        { name: 'AnimeTosho', enabled: true, healthy: false, stats: { success_rate: 0.45 } },
      ],
    },
    isLoading: false,
  }),
  useHealth: () => ({
    data: {
      services: { sonarr: 'connected', radarr: 'connected', ollama: 'ready' },
    },
    isLoading: false,
  }),
  useCleanupStats: () => ({
    data: { total_files: 8200, duplicate_files: 12, potential_savings_bytes: 52428800 },
    isLoading: false,
  }),
  useRefreshWanted: () => ({ mutate: mockRefresh, isPending: false }),
  useStartWantedBatch: () => ({ mutate: mockBatch, isPending: false }),
  useWantedBatchStatus: () => ({ data: { is_running: false } }),
  useWantedSummary: () => ({ data: { scan_running: false } }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@/lib/diskUtils', () => ({
  formatBytes: (bytes: number) => `${Math.round(bytes / 1024 / 1024)} MB`,
}))

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

beforeEach(() => {
  mockRefresh.mockClear()
  mockBatch.mockClear()
})

describe('DashboardSidebar', () => {
  it('renders the sidebar container', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('dashboard-sidebar')).toBeInTheDocument()
  })

  it('renders provider health panel', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-providers')).toBeInTheDocument()
    expect(screen.getByText('OpenSubtitles')).toBeInTheDocument()
    expect(screen.getByText('AnimeTosho')).toBeInTheDocument()
  })

  it('renders green dot for healthy provider', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('provider-dot-OpenSubtitles')).toHaveAttribute('data-healthy', 'true')
  })

  it('renders red dot for unhealthy provider', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('provider-dot-AnimeTosho')).toHaveAttribute('data-healthy', 'false')
  })

  it('renders service status panel', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-services')).toBeInTheDocument()
  })

  it('renders disk space panel with file count', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-disk')).toBeInTheDocument()
    expect(screen.getByTestId('disk-total-files')).toBeInTheDocument()
  })

  it('renders quick actions panel with scan button', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-actions')).toBeInTheDocument()
    expect(screen.getByTestId('btn-scan-library')).toBeInTheDocument()
  })

  it('calls refreshWanted when scan button is clicked', () => {
    wrap(<DashboardSidebar />)
    fireEvent.click(screen.getByTestId('btn-scan-library'))
    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('renders wanted list link to /wanted', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('link-wanted')).toHaveAttribute('href', '/wanted')
  })

  it('renders run now button in sidebar', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('btn-run-now-sidebar')).toBeInTheDocument()
  })

  it('renders logs link to /activity', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('link-logs')).toHaveAttribute('href', '/activity')
  })

  it('renders batch search button', () => {
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('btn-batch-search')).toBeInTheDocument()
  })
})
