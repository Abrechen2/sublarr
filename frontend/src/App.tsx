import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Dashboard } from '@/pages/Dashboard'
import { ActivityPage } from '@/pages/Activity'
import { WantedPage } from '@/pages/Wanted'
import { QueuePage } from '@/pages/Queue'
import { SettingsPage } from '@/pages/Settings'
import { LogsPage } from '@/pages/Logs'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5000,
      refetchOnWindowFocus: true,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 ml-56 p-8">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/activity" element={<ActivityPage />} />
              <Route path="/wanted" element={<WantedPage />} />
              <Route path="/queue" element={<QueuePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/logs" element={<LogsPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
