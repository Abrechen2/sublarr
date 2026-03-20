import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import React from 'react'

// Mock WebSocket context and hook
vi.mock('@/contexts/WebSocketContext', () => ({
  WebSocketProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => ({}),
}))

// Mock the layout components so we don't pull in all nav dependencies
vi.mock('@/components/layout/IconSidebar', () => ({
  IconSidebar: () => <nav data-testid="icon-sidebar" />,
}))
vi.mock('@/components/layout/BottomNav', () => ({
  BottomNav: () => null,
}))
vi.mock('@/components/layout/StatusBar', () => ({
  StatusBar: () => null,
}))

// Mock global modals / FABs
vi.mock('@/components/search/GlobalSearchModal', () => ({
  GlobalSearchModal: () => null,
}))
vi.mock('@/components/quick-actions/QuickActionsFAB', () => ({
  QuickActionsFAB: () => null,
}))
vi.mock('@/components/quick-actions/KeyboardShortcutsModal', () => ({
  KeyboardShortcutsModal: () => null,
}))

// Mock keyboard shortcuts hook (used inside BrowserRouter context)
vi.mock('@/hooks/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: () => undefined,
}))

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
  Trans: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock all lazy-loaded pages to avoid dynamic import issues in tests
vi.mock('@/pages/Dashboard', () => ({ Dashboard: () => <div>Dashboard</div> }))
vi.mock('@/pages/Activity', () => ({ ActivityPage: () => <div>Activity</div> }))
vi.mock('@/pages/Wanted', () => ({ WantedPage: () => <div>Wanted</div> }))
vi.mock('@/pages/Queue', () => ({ QueuePage: () => <div>Queue</div> }))
vi.mock('@/pages/Settings', () => ({ SettingsPage: () => <div>Settings</div> }))
vi.mock('@/pages/Logs', () => ({ LogsPage: () => <div>Logs</div> }))
vi.mock('@/pages/Statistics', () => ({ StatisticsPage: () => <div>Statistics</div> }))
vi.mock('@/pages/Library', () => ({ LibraryPage: () => <div>Library</div> }))
vi.mock('@/pages/SeriesDetail', () => ({ SeriesDetailPage: () => <div>SeriesDetail</div> }))
vi.mock('@/pages/History', () => ({ HistoryPage: () => <div>History</div> }))
vi.mock('@/pages/Blacklist', () => ({ BlacklistPage: () => <div>Blacklist</div> }))
vi.mock('@/pages/Tasks', () => ({ TasksPage: () => <div>Tasks</div> }))
vi.mock('@/pages/Plugins', () => ({ PluginsPage: () => <div>Plugins</div> }))
vi.mock('@/pages/NotFound', () => ({ NotFoundPage: () => <div>NotFound</div> }))
vi.mock('@/pages/Onboarding', () => ({ default: () => <div>Onboarding</div> }))

describe('Skip link', () => {
  it('has a skip-to-main-content link as first focusable element', async () => {
    const { default: App } = await import('@/App')
    const { container } = render(<App />)

    const skipLink = container.querySelector('a[href="#main-content"]')
    expect(skipLink).toBeInTheDocument()
    expect(skipLink).toHaveTextContent(/skip/i)
  })

  it('has a main element with id="main-content" as the link target', async () => {
    const { default: App } = await import('@/App')
    const { container } = render(<App />)

    const mainContent = container.querySelector('#main-content')
    expect(mainContent).toBeInTheDocument()
    expect(mainContent?.tagName.toLowerCase()).toBe('main')
  })

  it('skip link appears before sidebar in DOM order', async () => {
    const { default: App } = await import('@/App')
    const { container } = render(<App />)

    const skipLink = container.querySelector('a[href="#main-content"]')
    const sidebar = container.querySelector('[data-testid="icon-sidebar"]')
    expect(skipLink).toBeInTheDocument()
    expect(sidebar).toBeInTheDocument()

    // compareDocumentPosition: DOCUMENT_POSITION_FOLLOWING = 4 means sidebar comes after skipLink
    const position = skipLink!.compareDocumentPosition(sidebar!)
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
