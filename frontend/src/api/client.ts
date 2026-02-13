import axios from 'axios'
import type {
  HealthStatus, Stats, PaginatedJobs, Job, BatchState,
  BazarrStatus, LibraryInfo, AppConfig,
} from '@/lib/types'

const api = axios.create({
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

// ─── Health & Status ─────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await api.get('/health')
  return data
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get('/stats')
  return data
}

export async function getBazarrStatus(): Promise<BazarrStatus> {
  const { data } = await api.get('/status/bazarr')
  return data
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export async function getJobs(page = 1, perPage = 50, status?: string): Promise<PaginatedJobs> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (status) params.status = status
  const { data } = await api.get('/jobs', { params })
  return data
}

export async function getJobStatus(jobId: string): Promise<Job> {
  const { data } = await api.get(`/status/${jobId}`)
  return data
}

// ─── Translation ─────────────────────────────────────────────────────────────

export async function translateFile(filePath: string, force = false) {
  const { data } = await api.post('/translate', { file_path: filePath, force })
  return data
}

export async function translateSync(filePath: string, force = false) {
  const { data } = await api.post('/translate/sync', { file_path: filePath, force })
  return data
}

export async function translateWanted(maxEpisodes = 5) {
  const { data } = await api.post('/translate/wanted', { max_episodes: maxEpisodes })
  return data
}

// ─── Batch ───────────────────────────────────────────────────────────────────

export async function startBatch(directory: string, force = false, dryRun = false) {
  const { data } = await api.post('/batch', { directory, force, dry_run: dryRun })
  return data
}

export async function getBatchStatus(): Promise<BatchState> {
  const { data } = await api.get('/batch/status')
  return data
}

// ─── Config ──────────────────────────────────────────────────────────────────

export async function getConfig(): Promise<AppConfig> {
  const { data } = await api.get('/config')
  return data
}

export async function updateConfig(values: Record<string, unknown>) {
  const { data } = await api.put('/config', values)
  return data
}

// ─── Library ─────────────────────────────────────────────────────────────────

export async function getLibrary(): Promise<LibraryInfo> {
  const { data } = await api.get('/library')
  return data
}

// ─── Logs ────────────────────────────────────────────────────────────────────

export async function getLogs(lines = 200, level?: string) {
  const params: Record<string, unknown> = { lines }
  if (level) params.level = level
  const { data } = await api.get('/logs', { params })
  return data
}

export default api
