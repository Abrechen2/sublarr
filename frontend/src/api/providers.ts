import { api } from './core'
import type { ProviderInfo, ProviderStats } from '@/lib/types'

// ─── Providers ───────────────────────────────────────────────────────────────

export async function getProviders(): Promise<{ providers: ProviderInfo[] }> {
  const { data } = await api.get('/providers')
  return data
}

export async function testProvider(name: string): Promise<{ provider: string; healthy: boolean; message: string }> {
  const { data } = await api.post(`/providers/test/${name}`, {})
  return {
    provider: data.provider,
    healthy: data.health_check?.healthy ?? false,
    message: data.health_check?.message ?? 'No response',
  }
}

export async function getProviderStats(): Promise<ProviderStats> {
  const { data } = await api.get('/providers/stats')
  return data
}

export async function getProviderHealth(): Promise<Record<string, { healthy: boolean; circuit_state: string; rate_limited: boolean; last_error?: string }>> {
  const { data } = await api.get('/providers/health')
  return data
}

// ─── ffprobe cache ───────────────────────────────────────────────────────────

export async function getFfprobeStats(): Promise<{ count: number; oldest?: string; newest?: string }> {
  const { data } = await api.get('/cache/ffprobe/stats')
  return data
}

export async function triggerFfprobeCleanup(): Promise<{ removed: number }> {
  const { data } = await api.post('/cache/ffprobe/cleanup')
  return data
}

// ─── Database vacuum ─────────────────────────────────────────────────────────

export async function triggerDbVacuum(): Promise<{ status: string; message: string; duration_ms?: number }> {
  const { data } = await api.post('/database/vacuum')
  return data
}

export async function clearProviderCache(providerName?: string) {
  const body = providerName ? { provider_name: providerName } : {}
  const { data } = await api.post('/providers/cache/clear', body)
  return data
}

export async function enableProvider(name: string): Promise<{ status: string; provider: string; message: string }> {
  const { data } = await api.post(`/providers/${name}/enable`)
  return data
}

// ─── Marketplace ────────────────────────────────────────────────────────────────

export interface MarketplacePlugin {
  name: string
  version: string
  description: string
  author: string
  category: 'provider' | 'translation' | 'tool'
  url: string
  rating?: number
  downloads?: number
}

export interface MarketplacePluginInfo extends MarketplacePlugin {
  readme?: string
  changelog?: string
  dependencies?: string[]
  requirements?: string[]
}

export interface PluginInstallResult {
  status: 'installed' | 'failed'
  path?: string
  validation?: {
    valid: boolean
    errors: string[]
    warnings: string[]
  }
  error?: string
}

export async function getMarketplacePlugins(category?: string): Promise<{ plugins: MarketplacePlugin[] }> {
  const params: Record<string, unknown> = {}
  if (category) params.category = category
  const { data } = await api.get('/marketplace/plugins', { params })
  return data
}

export async function getMarketplacePlugin(pluginName: string): Promise<MarketplacePluginInfo> {
  const { data } = await api.get(`/marketplace/plugins/${pluginName}`)
  return data
}

export async function installMarketplacePlugin(
  pluginName: string,
  version?: string,
): Promise<PluginInstallResult> {
  const { data } = await api.post('/marketplace/install', { plugin_name: pluginName, version })
  return data
}

export async function uninstallMarketplacePlugin(pluginName: string): Promise<{ message: string }> {
  const { data } = await api.post('/marketplace/uninstall', { plugin_name: pluginName })
  return data
}

export async function checkMarketplaceUpdates(
  installedPlugins: string[],
): Promise<Record<string, { available: boolean; latest_version?: string }>> {
  const { data } = await api.get('/marketplace/updates', { params: { installed: installedPlugins } })
  return data.updates || {}
}

// ── v0.22 Marketplace types ────────────────────────────────────────────────
export interface MarketplaceBrowsePlugin {
  name: string
  display_name: string
  author: string
  version: string
  description: string
  github_url: string
  zip_url: string
  sha256: string
  capabilities: string[]
  min_sublarr_version: string
  is_official: boolean
}

export interface InstalledPlugin {
  name: string
  display_name: string
  version: string
  capabilities: string[]
  enabled: boolean
  installed_at: string
}

export async function getMarketplaceBrowse(): Promise<{ plugins: MarketplaceBrowsePlugin[] }> {
  const { data } = await api.get('/marketplace/plugins')
  return data
}

export async function refreshMarketplace(): Promise<{ plugins: MarketplaceBrowsePlugin[]; count: number }> {
  const { data } = await api.post('/marketplace/refresh')
  return data
}

export async function getInstalledPlugins(): Promise<{ installed: InstalledPlugin[] }> {
  const { data } = await api.get('/marketplace/installed')
  return data
}

export async function installBrowsePlugin(plugin: MarketplaceBrowsePlugin): Promise<{ status: string }> {
  const { data } = await api.post('/marketplace/install', {
    name: plugin.name,
    display_name: plugin.display_name,
    version: plugin.version,
    zip_url: plugin.zip_url,
    sha256: plugin.sha256,
    capabilities: plugin.capabilities,
  })
  return data
}

export async function uninstallBrowsePlugin(name: string): Promise<{ status: string }> {
  const { data } = await api.post('/marketplace/uninstall', { plugin_name: name })
  return data
}

// ─── Whisper API ──────────────────────────────────────────────────────────
export const getWhisperBackends = () => api.get('/whisper/backends').then(r => r.data)
export const testWhisperBackend = (name: string) => api.post(`/whisper/backends/test/${name}`).then(r => r.data)
export const getWhisperBackendConfig = (name: string) => api.get(`/whisper/backends/config/${name}`).then(r => r.data)
export const saveWhisperBackendConfig = (name: string, config: Record<string, string>) => api.put(`/whisper/backends/config/${name}`, config).then(r => r.data)
export const getWhisperConfig = () => api.get('/whisper/config').then(r => r.data)
export const saveWhisperConfig = (config: Record<string, unknown>) => api.put('/whisper/config', config).then(r => r.data)
export const getWhisperQueue = (params?: { status?: string; limit?: number }) => api.get('/whisper/queue', { params }).then(r => r.data)
export const getWhisperJob = (jobId: string) => api.get(`/whisper/jobs/${jobId}`).then(r => r.data)
export const submitWhisperJob = (data: { file_path: string; language?: string }) => api.post('/whisper/transcribe', data).then(r => r.data)
export const deleteWhisperJob = (jobId: string) => api.delete(`/whisper/jobs/${jobId}`).then(r => r.data)
export const getWhisperStats = () => api.get('/whisper/stats').then(r => r.data)
export const submitWhisperJobWithTrack = (data: { file_path: string; language?: string; audio_track_index?: number | null }) =>
  api.post('/whisper/transcribe', data).then(r => r.data)

// --- Phase 25-02: AniDB Absolute Episode Order ---

export async function getAnidbMappingStatus(): Promise<{
  last_sync?: string
  entry_count?: number
  status: string
}> {
  const response = await api.get('/anidb-mapping/status')
  return response.data
}

export async function refreshAnidbMapping(): Promise<{ success: boolean; message?: string }> {
  const response = await api.post('/anidb-mapping/refresh')
  return response.data
}
