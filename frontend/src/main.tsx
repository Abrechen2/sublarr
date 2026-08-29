import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './i18n'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { bootstrapApiKey } from '@/api/client'
import App from './App.tsx'
import './index.css'
import { withBase } from '@/basePath'

// Register Service Worker for PWA (production only — dev HMR breaks with SW caching)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(withBase('/sw.js'))
      .then(() => {
        // registered
      })
      .catch((error) => {
        console.error('Service Worker registration failed:', error)
      })
  })
}

// Fix 8: Fail fast with a clear error rather than a runtime crash on non-null assertion
const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('Root element #root not found. Check index.html.')
}

// Bootstrap API key before rendering — fetches from backend if not in localStorage
bootstrapApiKey().finally(() => {
  createRoot(rootEl).render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>,
  )
})
