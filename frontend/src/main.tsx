import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './i18n'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import App from './App.tsx'
import './index.css'

// Register Service Worker for PWA (production only — dev HMR breaks with SW caching)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        console.log('Service Worker registered:', registration.scope)
      })
      .catch((error) => {
        console.error('Service Worker registration failed:', error)
      })
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
