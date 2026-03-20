import { lazy, Suspense, useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IconSidebar } from '@/components/layout/IconSidebar'
import { BottomNav } from '@/components/layout/BottomNav'
import { StatusBar } from '@/components/layout/StatusBar'
import { ToastContainer, toast } from '@/components/shared/Toast'
import {
  PageSkeleton,
  LibrarySkeleton,
  TableSkeleton,
  ListSkeleton,
  FormSkeleton,
} from '@/components/shared/PageSkeleton'
import { useWebSocket } from '@/hooks/useWebSocket'
import { WebSocketProvider } from '@/contexts/WebSocketContext'
import { GlobalSearchModal } from '@/components/search/GlobalSearchModal'
import { QuickActionsFAB } from '@/components/quick-actions/QuickActionsFAB'
import { KeyboardShortcutsModal } from '@/components/quick-actions/KeyboardShortcutsModal'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { AuthGuard } from '@/components/auth/AuthGuard'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

// Route-level code splitting: each page is lazy-loaded as a separate chunk
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })))
const ActivityPage = lazy(() => import('@/pages/Activity').then(m => ({ default: m.ActivityPage })))
const WantedPage = lazy(() => import('@/pages/Wanted').then(m => ({ default: m.WantedPage })))
const QueuePage = lazy(() => import('@/pages/Queue').then(m => ({ default: m.QueuePage })))
const SettingsPage = lazy(() => import('@/pages/Settings').then(m => ({ default: m.SettingsPage })))
const LogsPage = lazy(() => import('@/pages/Logs').then(m => ({ default: m.LogsPage })))
const StatisticsPage = lazy(() => import('@/pages/Statistics').then(m => ({ default: m.StatisticsPage })))
const LibraryPage = lazy(() => import('@/pages/Library').then(m => ({ default: m.LibraryPage })))
const SeriesDetailPage = lazy(() => import('@/pages/SeriesDetail').then(m => ({ default: m.SeriesDetailPage })))
const HistoryPage = lazy(() => import('@/pages/History').then(m => ({ default: m.HistoryPage })))
const BlacklistPage = lazy(() => import('@/pages/Blacklist').then(m => ({ default: m.BlacklistPage })))
const TasksPage = lazy(() => import('@/pages/Tasks').then(m => ({ default: m.TasksPage })))
const PluginsPage = lazy(() => import('@/pages/Plugins').then(m => ({ default: m.PluginsPage })))
const NotFoundPage = lazy(() => import('@/pages/NotFound').then(m => ({ default: m.NotFoundPage })))
const Onboarding = lazy(() => import('@/pages/Onboarding'))
const SetupPage = lazy(() => import('@/pages/Setup').then(m => ({ default: m.SetupPage })))
const LoginPage = lazy(() => import('@/pages/Login').then(m => ({ default: m.LoginPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60_000,
      refetchOnWindowFocus: true,
    },
  },
})

function AnimatedRoutes() {
  const location = useLocation()
  const isAuthRoute = location.pathname === '/setup' || location.pathname === '/login'

  if (isAuthRoute) {
    return (
      <Routes location={location}>
        <Route path="/setup" element={<Suspense fallback={<PageSkeleton />}><SetupPage /></Suspense>} />
        <Route path="/login" element={<Suspense fallback={<PageSkeleton />}><LoginPage /></Suspense>} />
      </Routes>
    )
  }

  return (
    <AuthGuard>
      <div key={location.pathname} className="page-enter">
        <Routes location={location}>
          <Route path="/" element={<Suspense fallback={<PageSkeleton />}><Dashboard /></Suspense>} />
          <Route path="/library" element={<ErrorBoundary><Suspense fallback={<LibrarySkeleton />}><LibraryPage /></Suspense></ErrorBoundary>} />
          <Route path="/library/series/:id" element={<Suspense fallback={<PageSkeleton />}><SeriesDetailPage /></Suspense>} />
          <Route path="/activity" element={<Suspense fallback={<PageSkeleton />}><ActivityPage /></Suspense>} />
          <Route path="/wanted" element={<ErrorBoundary><Suspense fallback={<ListSkeleton />}><WantedPage /></Suspense></ErrorBoundary>} />
          <Route path="/queue" element={<Suspense fallback={<TableSkeleton />}><QueuePage /></Suspense>} />
          <Route path="/history" element={<Suspense fallback={<TableSkeleton />}><HistoryPage /></Suspense>} />
          <Route path="/blacklist" element={<Suspense fallback={<TableSkeleton />}><BlacklistPage /></Suspense>} />
          <Route path="/settings" element={<ErrorBoundary><Suspense fallback={<FormSkeleton />}><SettingsPage /></Suspense></ErrorBoundary>} />
          <Route path="/statistics" element={<Suspense fallback={<PageSkeleton />}><StatisticsPage /></Suspense>} />
          <Route path="/tasks" element={<Suspense fallback={<PageSkeleton />}><TasksPage /></Suspense>} />
          <Route path="/plugins" element={<Suspense fallback={<PageSkeleton />}><PluginsPage /></Suspense>} />
          <Route path="/logs" element={<Suspense fallback={<PageSkeleton />}><LogsPage /></Suspense>} />
          <Route path="/onboarding" element={<Suspense fallback={<PageSkeleton />}><Onboarding /></Suspense>} />
          <Route path="*" element={<Suspense fallback={<PageSkeleton />}><NotFoundPage /></Suspense>} />
        </Routes>
      </div>
    </AuthGuard>
  )
}

function GlobalWebSocketListener() {
  useWebSocket({
    onWebhookReceived: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Webhook: ${String(d.title ?? 'Download received')}`, 'info')
    },
    onWebhookCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Auto-processed: ${String(d.title ?? d.file_path ?? 'file')}`, 'success')
    },
    onUpgradeCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Upgraded: ${String(d.file_path ?? 'subtitle')}`, 'success')
    },
    onWantedSearchCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Search complete: ${String(d.found ?? 0)} found`, 'info')
    },
    onRetranslationCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      const count = String(d.count ?? d.succeeded ?? 0)
      toast(`Re-translated: ${count} files`, 'success')
    },
    onConfigUpdated: (data: unknown) => {
      const d = data as Record<string, unknown>
      const keys = d.updated_keys as string[] | undefined
      toast(`Config updated${keys ? `: ${keys.join(', ')}` : ''}`, 'info')
    },
  })

  return null
}

/** Renders no UI -- just registers global keyboard shortcuts inside BrowserRouter context. */
function GlobalShortcuts({ onToggleShortcutsModal }: { onToggleShortcutsModal: () => void }) {
  useKeyboardShortcuts({ onToggleShortcutsModal })
  return null
}

function AppInner({
  searchOpen,
  setSearchOpen,
  shortcutsModalOpen,
  toggleShortcutsModal,
  closeShortcutsModal,
}: {
  searchOpen: boolean
  setSearchOpen: (v: boolean) => void
  shortcutsModalOpen: boolean
  toggleShortcutsModal: () => void
  closeShortcutsModal: () => void
}) {
  const location = useLocation()
  const isAuthRoute = location.pathname === '/setup' || location.pathname === '/login'

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded"
        style={{ backgroundColor: 'var(--accent)', color: '#fff' }}
      >
        Skip to main content
      </a>
      <GlobalWebSocketListener />
      <GlobalShortcuts onToggleShortcutsModal={toggleShortcutsModal} />
      {isAuthRoute ? (
        <AnimatedRoutes />
      ) : (
        <div className="flex min-h-screen">
          <IconSidebar />
          <main
            id="main-content"
            className="flex-1 min-w-0 min-h-screen ml-0 md:ml-[60px] px-4 py-4 md:px-8 md:py-6 pb-20 md:pb-10"
          >
            <AnimatedRoutes />
          </main>
          <StatusBar />
          <BottomNav />
        </div>
      )}
      {!isAuthRoute && (
        <>
          <GlobalSearchModal open={searchOpen} onOpenChange={setSearchOpen} />
          <QuickActionsFAB />
          <KeyboardShortcutsModal open={shortcutsModalOpen} onClose={closeShortcutsModal} />
        </>
      )}
      <ToastContainer />
    </>
  )
}

function App() {
  const [searchOpen, setSearchOpen] = useState(false)
  const [shortcutsModalOpen, setShortcutsModalOpen] = useState(false)

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      setSearchOpen((prev) => !prev)
    }
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const toggleShortcutsModal = useCallback(() => {
    setShortcutsModalOpen((prev) => !prev)
  }, [])

  const closeShortcutsModal = useCallback(() => {
    setShortcutsModalOpen(false)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
      <BrowserRouter>
        <AppInner
          searchOpen={searchOpen}
          setSearchOpen={setSearchOpen}
          shortcutsModalOpen={shortcutsModalOpen}
          toggleShortcutsModal={toggleShortcutsModal}
          closeShortcutsModal={closeShortcutsModal}
        />
      </BrowserRouter>
      </WebSocketProvider>
    </QueryClientProvider>
  )
}

export default App
