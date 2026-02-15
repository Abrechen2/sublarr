import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { ToastContainer, toast } from '@/components/shared/Toast'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Dashboard } from '@/pages/Dashboard'
import { ActivityPage } from '@/pages/Activity'
import { WantedPage } from '@/pages/Wanted'
import { QueuePage } from '@/pages/Queue'
import { SettingsPage } from '@/pages/Settings'
import { LogsPage } from '@/pages/Logs'
import { StatisticsPage } from '@/pages/Statistics'
import { LibraryPage } from '@/pages/Library'
import { SeriesDetailPage } from '@/pages/SeriesDetail'
import { HistoryPage } from '@/pages/History'
import { BlacklistPage } from '@/pages/Blacklist'
import { NotFoundPage } from '@/pages/NotFound'
import Onboarding from '@/pages/Onboarding'

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
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
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
