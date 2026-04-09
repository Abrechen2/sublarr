import { api } from './core'
import type {
  AppConfig, LanguageProfile, HookConfig, WebhookConfig,
  MediaServerType, MediaServerInstance, MediaServerTestResult, MediaServerHealthResult,
  AuthStatus,
} from '@/lib/types'

// ─── Config ──────────────────────────────────────────────────────────────────

export async function getConfig(): Promise<AppConfig> {
  const { data } = await api.get('/config')
  return data
}

export async function updateConfig(values: Record<string, unknown>) {
  const { data } = await api.put('/config', values)
  return data
}

// ─── Config Export/Import ────────────────────────────────────────────────────

export async function exportConfig(): Promise<AppConfig> {
  const { data } = await api.get('/config/export')
  return data
}

export async function importConfig(config: Record<string, unknown>): Promise<{ status: string; imported_keys: string[]; skipped_secrets: string[] }> {
  const { data } = await api.post('/config/import', config)
  return data
}

// ─── Language Profiles ───────────────────────────────────────────────────────

export async function getLanguageProfiles(): Promise<LanguageProfile[]> {
  const { data } = await api.get('/language-profiles')
  return data.profiles
}

export async function createLanguageProfile(profile: Omit<LanguageProfile, 'id' | 'is_default'>): Promise<LanguageProfile> {
  const { data } = await api.post('/language-profiles', profile)
  return data
}

export async function updateLanguageProfile(id: number, profile: Partial<LanguageProfile>): Promise<LanguageProfile> {
  const { data } = await api.put(`/language-profiles/${id}`, profile)
  return data
}

export async function deleteLanguageProfile(id: number): Promise<void> {
  await api.delete(`/language-profiles/${id}`)
}

export async function assignProfile(type: 'series' | 'movie', arrId: number, profileId: number): Promise<void> {
  await api.put('/language-profiles/assign', { type, arr_id: arrId, profile_id: profileId })
}

export async function setProfileAsDefaultForAll(id: number): Promise<LanguageProfile> {
  const { data } = await api.post(`/language-profiles/${id}/set-as-default-for-all`)
  return data.profile
}

// ─── Events & Hooks ──────────────────────────────────────────────────────

export const getEventCatalog = () => api.get('/events/catalog').then(r => r.data)
export const getHookConfigs = (eventName?: string) => api.get('/hooks', { params: eventName ? { event_name: eventName } : {} }).then(r => r.data)
export const createHookConfig = (data: Partial<HookConfig>) => api.post('/hooks', data).then(r => r.data)
export const updateHookConfig = (id: number, data: Partial<HookConfig>) => api.put(`/hooks/${id}`, data).then(r => r.data)
export const deleteHookConfig = (id: number) => api.delete(`/hooks/${id}`)
export const testHook = (id: number) => api.post(`/hooks/${id}/test`).then(r => r.data)
export const getWebhookConfigs = (eventName?: string) => api.get('/webhooks', { params: eventName ? { event_name: eventName } : {} }).then(r => r.data)
export const createWebhookConfig = (data: Partial<WebhookConfig>) => api.post('/webhooks', data).then(r => r.data)
export const updateWebhookConfig = (id: number, data: Partial<WebhookConfig>) => api.put(`/webhooks/${id}`, data).then(r => r.data)
export const deleteWebhookConfig = (id: number) => api.delete(`/webhooks/${id}`)
export const testWebhook = (id: number) => api.post(`/webhooks/${id}/test`).then(r => r.data)
export const getHookLogs = (params?: { hook_id?: number; webhook_id?: number; limit?: number }) => api.get('/hooks/logs', { params }).then(r => r.data)
export const clearHookLogs = () => api.delete('/hooks/logs')
export const getScoringWeights = () => api.get('/scoring/weights').then(r => r.data)
export const updateScoringWeights = (data: { episode?: Record<string, number>; movie?: Record<string, number> }) => api.put('/scoring/weights', data).then(r => r.data)
export const resetScoringWeights = () => api.delete('/scoring/weights')
export const getProviderModifiers = () => api.get('/scoring/modifiers').then(r => r.data)
export const updateProviderModifiers = (data: Record<string, number>) => api.put('/scoring/modifiers', data).then(r => r.data)
export const deleteProviderModifier = (name: string) => api.delete(`/scoring/modifiers/${name}`)
export const getScoringPresets = () => api.get('/scoring/presets').then(r => r.data)
export const getScoringPreset = (name: string) => api.get(`/scoring/presets/${encodeURIComponent(name)}`).then(r => r.data)
export const importScoringPreset = (data: Record<string, unknown>) => api.post('/scoring/presets/import', data).then(r => r.data)

// ─── Media Servers ──────────────────────────────────────────────────────────

export async function getMediaServerTypes(): Promise<MediaServerType[]> {
  const { data } = await api.get('/mediaservers/types')
  return data
}

export async function getMediaServerInstances(): Promise<MediaServerInstance[]> {
  const { data } = await api.get('/mediaservers/instances')
  return data
}

export async function saveMediaServerInstances(instances: MediaServerInstance[]): Promise<MediaServerInstance[]> {
  const { data } = await api.put('/mediaservers/instances', instances)
  return data
}

export async function testMediaServer(config: Record<string, unknown>): Promise<MediaServerTestResult> {
  const { data } = await api.post('/mediaservers/test', config)
  return data
}

export async function getMediaServerHealth(): Promise<MediaServerHealthResult[]> {
  const { data } = await api.get('/mediaservers/health')
  return data
}

// ─── Instances (Multi-Library) ────────────────────────────────────────────────

export interface InstanceConfig {
  name: string
  url: string
  api_key: string
  path_mapping?: string
}

export async function getSonarrInstances(): Promise<InstanceConfig[]> {
  const { data } = await api.get('/sonarr/instances')
  return data
}

export async function getRadarrInstances(): Promise<InstanceConfig[]> {
  const { data } = await api.get('/radarr/instances')
  return data
}

export async function testSonarrInstance(config: { url: string; api_key: string }): Promise<{ healthy: boolean; message: string }> {
  const { data } = await api.post('/sonarr/instances/test', config)
  return data
}

export async function testRadarrInstance(config: { url: string; api_key: string }): Promise<{ healthy: boolean; message: string }> {
  const { data } = await api.post('/radarr/instances/test', config)
  return data
}

// ─── Onboarding ──────────────────────────────────────────────────────────────

export async function getOnboardingStatus(): Promise<{
  completed: boolean
  has_sonarr: boolean
  has_radarr: boolean
  has_ollama: boolean
  has_providers: boolean
}> {
  const { data } = await api.get('/onboarding/status')
  return data
}

export async function completeOnboarding(): Promise<{ status: string }> {
  const { data } = await api.post('/onboarding/complete')
  return data
}

// ─── API Key Management ──────────────────────────────────────────────────────

export async function getApiKeys(): Promise<{ services: import('@/lib/types').ApiKeyService[] }> {
  const { data } = await api.get('/api-keys')
  return data
}

export async function getApiKeyService(service: string): Promise<import('@/lib/types').ApiKeyService> {
  const { data } = await api.get(`/api-keys/${service}`)
  return data
}

export async function updateApiKey(service: string, keyName: string, value: string): Promise<{ status: string }> {
  const { data } = await api.put(`/api-keys/${service}`, { [keyName]: value })
  return data
}

export async function testApiKey(service: string): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post(`/api-keys/${service}/test`)
  return data
}

export async function exportApiKeys(): Promise<Blob> {
  const { data } = await api.post('/api-keys/export', {}, { responseType: 'blob' })
  return data
}

export async function importApiKeys(file: File): Promise<{ status: string; imported: number; skipped: number }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api-keys/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function importBazarrConfig(file: File): Promise<import('@/lib/types').BazarrMigrationPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api-keys/import/bazarr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function confirmBazarrImport(preview: import('@/lib/types').BazarrMigrationPreview): Promise<{ status: string; imported: number }> {
  const { data } = await api.post('/api-keys/import/bazarr/confirm', preview)
  return data
}

// ─── UI Auth ─────────────────────────────────────────────────────────────────

export async function getAuthStatus(): Promise<AuthStatus> {
  const { data } = await api.get('/auth/status')
  return data
}

export async function setupAuth(body: { action: 'set_password'; password: string } | { action: 'disable' }): Promise<void> {
  await api.post('/auth/setup', body)
}

export async function login(password: string): Promise<void> {
  await api.post('/auth/login', { password })
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout')
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword })
}

export async function toggleAuth(enabled: boolean): Promise<void> {
  await api.post('/auth/toggle', { enabled })
}

/** Fetch the streaming_enabled flag from config. */
export async function getStreamingEnabled(): Promise<boolean> {
  const { data } = await api.get<{ streaming_enabled?: boolean }>('/config')
  return data.streaming_enabled ?? true
}

/** Returns the URL for streaming a media file. Not a fetch — just a URL builder.
 *  Appends the API key as a query param so browser-native requests (<video>, libass-wasm)
 *  can authenticate without custom headers. */
export function getMediaStreamUrl(filePath: string): string {
  const encoded = encodeURIComponent(filePath)
  const apiKey = localStorage.getItem('sublarr_api_key')
  const auth = apiKey ? `&apikey=${encodeURIComponent(apiKey)}` : ''
  return `/api/v1/media/stream?path=${encoded}${auth}`
}
