import axios from 'axios'

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Add API key interceptor if configured
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('sublarr_api_key')
  if (apiKey) {
    config.headers['X-Api-Key'] = apiKey
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If we're in development and the backend is unreachable/not set up, return robust mock data
    // to match the visual mockups during UI development.
    if (import.meta.env.DEV && (error.code === 'ERR_NETWORK' || [404, 500, 502, 503, 504].includes(error.response?.status))) {
      const url = error.config.url || ''
      console.log(`[MOCK] Returning mock data for failed request: ${url}`)

      if (url.includes('/auth/bootstrap')) return Promise.resolve({ data: { api_key: 'mock-key' } })
      if (url.includes('/auth/setup')) return Promise.resolve({ data: { status: 'success' } })
      if (url.includes('/auth/status')) return Promise.resolve({ data: { setup_required: false, configured: true } })
      if (url.includes('/onboarding/status')) {
        return Promise.resolve({ data: {
          completed: true, has_sonarr: true, has_radarr: true, has_ollama: true, has_providers: true
        } })
      }

      if (url.includes('/config')) {
        return Promise.resolve({ data: {
          source_language: 'en', target_language: 'de', media_path: '/media', port: 5765, log_level: 'INFO'
        } })
      }
      if (url.includes('/providers/stats')) {
        return Promise.resolve({ data: { cache: {} } })
      }
      if (url.includes('/providers')) {
        return Promise.resolve({ data: {
          providers: [
            { name: 'Jimaku', enabled: true, healthy: true, stats: { success_rate: 89 } },
            { name: 'OpenSubs', enabled: true, healthy: true, stats: { success_rate: 76 } },
            { name: 'Subdl', enabled: true, healthy: true, stats: { success_rate: 65 } },
            { name: 'Animetosho', enabled: true, healthy: true, stats: { success_rate: 42 } },
          ]
        } })
      }
      if (url.includes('/health')) {
        return Promise.resolve({ data: {
          services: {
            sonarr: 'Connected',
            radarr: 'Connected',
            automation: 'Running',
            translation: 'Off'
          }
        } })
      }
      if (url.includes('/cleanup/rules')) {
        return Promise.resolve({ data: [] })
      }
      if (url.includes('/cleanup/stats')) {
        return Promise.resolve({ data: {
          total_files: 0, total_size_bytes: 0, by_format: [],
          duplicate_files: 0, duplicate_size_bytes: 0, potential_savings_bytes: 0, trends: []
        } })
      }
      if (url.includes('/stats')) {
        return Promise.resolve({ data: {
          total_subtitles: 12,
          downloads_today: 2,
          average_score: 92.4,
          low_score_count: 1
        } })
      }
      if (url.includes('/wanted/summary')) {
        return Promise.resolve({ data: { total: 1 } })
      }
      if (url.includes('/wanted')) {
        return Promise.resolve({ data: { items: [], total: 0 } })
      }
      if (url.includes('/jobs')) {
        return Promise.resolve({ data: {
          data: [
            { id: '1', status: 'completed', file_path: '/media/Anime/Solo Leveling/S01E01.mkv', created_at: new Date().toISOString() },
            { id: '2', status: 'completed', file_path: '/media/Anime/Jujutsu Kaisen/S02E05.mkv', created_at: new Date(Date.now()-60000).toISOString() },
            { id: '3', status: 'completed', file_path: '/media/Anime/Mushoku Tensei/S02E11.mkv', created_at: new Date(Date.now()-120000).toISOString() },
          ],
          total: 3
        } })
      }

      if (url.includes('/filter-presets')) {
        return Promise.resolve({ data: [] })
      }

      // Fallback empty object for other fails
      return Promise.resolve({ data: {} })
    }

    if (error.response?.status === 401 && !error.config.url?.includes('/auth/')) {
      // A 401 despite a stored key means the key is stale (e.g. the backend
      // regenerated it). Drop it so bootstrapApiKey() fetches a fresh one on
      // the reload — otherwise its early-return keeps re-sending the dead key
      // and the app loops between /login and the dashboard forever.
      localStorage.removeItem('sublarr_api_key')
      // Only hard-navigate when we are NOT already on /login. Redirecting
      // /login → /login is a full page reload, so a single background 401
      // (e.g. a request that raced the freshly-issued session cookie) puts
      // the UI into an endless reload loop instead of showing the form once.
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

/**
 * Bootstrap: fetch the API key from the backend on first load.
 * The /auth/bootstrap endpoint is only accessible from localhost or an
 * authenticated UI session, so the key is never exposed to external callers.
 * Once retrieved it is stored in localStorage and picked up by the interceptor.
 *
 * When UI auth is disabled, /auth/login is a no-op that just establishes a
 * session cookie (no password needed) — calling it first lets /auth/bootstrap
 * succeed over LAN instead of only from localhost.
 */
export async function bootstrapApiKey(): Promise<void> {
  if (localStorage.getItem('sublarr_api_key')) return
  try {
    const status = await axios.get('/api/v1/auth/status')
    if (status.data?.enabled === false && !status.data?.authenticated) {
      await axios.post('/api/v1/auth/login', {})
    }
  } catch {
    // Status check failed — still attempt bootstrap below as-is
  }
  try {
    const res = await axios.get('/api/v1/auth/bootstrap')
    const key: string = res.data?.api_key
    if (key) {
      localStorage.setItem('sublarr_api_key', key)
    }
  } catch {
    // Non-local access or auth required — key must be set manually
  }
}
