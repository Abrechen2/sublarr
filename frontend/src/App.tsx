import { lazy, Suspense, useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { IconSidebar } from '@/components/layout/IconSidebar'
import { UpdateBanner } from '@/components/layout/UpdateBanner'
import { BottomNav } from '@/components/layout/BottomNav'
import { StatusBar } from '@/components/layout/StatusBar'
import { ToastContainer, toast } from '@/components/shared/Toast'
import {
  PageSkeleton,
  LibrarySkeleton,
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
import FirstRunWizard, { shouldShowWizard } from '@/components/Setup/FirstRunWizard'
import { useSetupStatus } from '@/hooks/useSystemApi'
import { useConfig } from '@/hooks/useApi'

// Route-level code splitting: each page is lazy-loaded as a separate chunk
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })))
const ActivityPage = lazy(() => import('@/pages/ActivityPage').then(m => ({ default: m.ActivityPage })))
const SettingsPage = lazy(() => import('@/pages/Settings').then(m => ({ default: m.SettingsPage })))
const LibraryPage = lazy(() => import('@/pages/Library').then(m => ({ default: m.LibraryPage })))
const SeriesDetailPage = lazy(() => import('@/pages/SeriesDetail').then(m => ({ default: m.SeriesDetailPage })))
const NotFoundPage = lazy(() => import('@/pages/NotFound').then(m => ({ default: m.NotFoundPage })))
const Onboarding = lazy(() => import('@/pages/Onboarding'))
const SetupPage = lazy(() => import('@/pages/Setup').then(m => ({ default: m.SetupPage })))
const LoginPage = lazy(() => import('@/pages/Login').then(m => ({ default: m.LoginPage })))
const MovieDetailPage = lazy(() => import('@/pages/MovieDetail').then(m => ({ default: m.MovieDetailPage })))
const StatisticsPage = lazy(() => import('@/pages/StatisticsPage').then(m => ({ default: m.StatisticsPage })))
const WantedPage = lazy(() => import('@/pages/Wanted').then(m => ({ default: m.WantedPage })))
const TrashPage = lazy(() => import('@/pages/Trash').then(m => ({ default: m.TrashPage })))
const LogsPage = lazy(() => import('@/pages/Logs').then(m => ({ default: m.LogsPage })))

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
          <Route path="/wanted" element={<Suspense fallback={<PageSkeleton />}><WantedPage /></Suspense>} />
          <Route path="/trash" element={<Suspense fallback={<PageSkeleton />}><TrashPage /></Suspense>} />
          {/* Redirect old routes to unified Activity page tabs */}
          <Route path="/queue" element={<Navigate to="/activity?tab=queue" replace />} />
          <Route path="/history" element={<Navigate to="/activity?tab=history" replace />} />
          <Route path="/blacklist" element={<Navigate to="/activity?tab=blacklist" replace />} />
          <Route path="/settings/*" element={<ErrorBoundary><Suspense fallback={<FormSkeleton />}><SettingsPage /></Suspense></ErrorBoundary>} />
          <Route path="/language-profiles" element={<Navigate to="/settings/subtitles/languages" replace />} />
          <Route path="/movies/:id" element={<Suspense fallback={<FormSkeleton />}><MovieDetailPage /></Suspense>} />
          <Route path="/statistics" element={<Suspense fallback={<PageSkeleton />}><StatisticsPage /></Suspense>} />
          {/* Redirect old standalone pages into settings sub-routes */}
          <Route path="/tasks" element={<Navigate to="/settings/automation" replace />} />
          <Route path="/plugins" element={<Navigate to="/settings/providers" replace />} />
          <Route path="/logs" element={<Suspense fallback={<PageSkeleton />}><LogsPage /></Suspense>} />
          <Route path="/onboarding" element={<Suspense fallback={<PageSkeleton />}><Onboarding /></Suspense>} />
          <Route path="*" element={<Suspense fallback={<PageSkeleton />}><NotFoundPage /></Suspense>} />
        </Routes>
      </div>
    </AuthGuard>
  )
}

function GlobalWebSocketListener() {
  const { t } = useTranslation('common')

  useWebSocket({
    onWebhookReceived: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(t('global_toasts.webhook_received', { title: String(d.title ?? t('global_toasts.download_received')) }), 'info')
    },
    onWebhookCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(t('global_toasts.auto_processed', { title: String(d.title ?? d.file_path ?? t('global_toasts.file_fallback')) }), 'success')
    },
    onUpgradeCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(t('global_toasts.upgraded', { file: String(d.file_path ?? t('global_toasts.subtitle_fallback')) }), 'success')
    },
    onWantedSearchCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(t('global_toasts.search_complete', { count: Number(d.found ?? 0) }), 'info')
    },
    onRetranslationCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(t('global_toasts.retranslated', { count: Number(d.count ?? d.succeeded ?? 0) }), 'success')
    },
    onConfigUpdated: (data: unknown) => {
      const d = data as Record<string, unknown>
      const keys = d.updated_keys as string[] | undefined
      toast(
        keys
          ? t('global_toasts.config_updated_keys', { keys: keys.join(', ') })
          : t('global_toasts.config_updated'),
        'info'
      )
    },
  })

  return null
}

/** Applies the persisted interface_language setting to the i18n runtime once
 *  the config loads, so the stored setting and the rendered language cannot
 *  drift apart (they were previously two disconnected sources of truth). */
function InterfaceLanguageSync() {
  const { i18n } = useTranslation()
  const { data: config } = useConfig()

  useEffect(() => {
    const lang = (config as Record<string, unknown> | undefined)?.interface_language
    if ((lang === 'de' || lang === 'en') && !i18n.language?.startsWith(lang)) {
      i18n.changeLanguage(lang)
    }
  }, [config, i18n])

  return null
}

/** Renders no UI -- just registers global keyboard shortcuts inside BrowserRouter context. */
function GlobalShortcuts({ onToggleShortcutsModal }: { onToggleShortcutsModal: () => void }) {
  useKeyboardShortcuts({ onToggleShortcutsModal })
  return null
}

/** Renders the first-run wizard modal when the backend says it hasn't been
 *  completed and the user hasn't postponed it within the last 7 days. */
function FirstRunWizardMount() {
  const { data: setupStatus } = useSetupStatus()
  const [wizardOpen, setWizardOpen] = useState(false)

  useEffect(() => {
    if (shouldShowWizard(setupStatus)) {
      setWizardOpen(true)
    }
  }, [setupStatus])

  if (!wizardOpen) return null
  return <FirstRunWizard onClose={() => setWizardOpen(false)} />
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
  const { t } = useTranslation('common')
  const isAuthRoute = location.pathname === '/setup' || location.pathname === '/login'

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded"
        style={{ backgroundColor: 'var(--accent)', color: '#fff' }}
      >
        {t('skip_to_main_content')}
      </a>
      {!isAuthRoute && <InterfaceLanguageSync />}
      <GlobalWebSocketListener />
      <GlobalShortcuts onToggleShortcutsModal={toggleShortcutsModal} />
      {isAuthRoute ? (
        <AnimatedRoutes />
      ) : (
        <div className="flex flex-col min-h-screen">
          <UpdateBanner />
          <div className="flex flex-1 min-h-0">
            <IconSidebar />
            {/* min-h-screen kept intentionally: avoids content reflow when the banner is dismissed */}
            <main
              id="main-content"
              className="flex-1 min-w-0 min-h-screen main-content-area"
              style={{ padding: '24px 32px 60px', maxWidth: '1680px' }}
            >
              <AnimatedRoutes />
            </main>
            <StatusBar />
            <BottomNav />
          </div>
        </div>
      )}
      {!isAuthRoute && (
        <>
          <GlobalSearchModal open={searchOpen} onOpenChange={setSearchOpen} />
          <QuickActionsFAB />
          <KeyboardShortcutsModal open={shortcutsModalOpen} onClose={closeShortcutsModal} />
          <FirstRunWizardMount />
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
