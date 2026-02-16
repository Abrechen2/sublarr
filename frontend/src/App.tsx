import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { ToastContainer, toast } from '@/components/shared/Toast'
import { PageSkeleton } from '@/components/shared/PageSkeleton'
import { useWebSocket } from '@/hooks/useWebSocket'

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
const NotFoundPage = lazy(() => import('@/pages/NotFound').then(m => ({ default: m.NotFoundPage })))
const Onboarding = lazy(() => import('@/pages/Onboarding'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5000,
      refetchOnWindowFocus: true,
    },
  },
})

function AnimatedRoutes() {
  const location = useLocation()

  return (
    <div key={location.pathname} className="page-enter">
      <Suspense fallback={<PageSkeleton />}>
        <Routes location={location}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/series/:id" element={<SeriesDetailPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/wanted" element={<WantedPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/blacklist" element={<BlacklistPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/statistics" element={<StatisticsPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </div>
  )
}

function GlobalWebSocketListener() {
  useWebSocket({
    onWebhookReceived: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Webhook: ${d.title || 'Download received'}`, 'info')
    },
    onWebhookCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Auto-processed: ${d.title || d.file_path || 'file'}`, 'success')
    },
    onUpgradeCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Upgraded: ${d.file_path || 'subtitle'}`, 'success')
    },
    onWantedSearchCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      toast(`Search complete: ${d.found || 0} found`, 'info')
    },
    onRetranslationCompleted: (data: unknown) => {
      const d = data as Record<string, unknown>
      const count = d.count || d.succeeded || 0
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

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <GlobalWebSocketListener />
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 p-4 md:p-6 lg:p-8 pt-16 md:pt-6 lg:pt-8 min-h-screen">
            <AnimatedRoutes />
          </main>
        </div>
        <ToastContainer />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
