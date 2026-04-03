import { api } from './core'
import type { TranslationBackendInfo, BackendConfig, BackendHealthResult, BackendStats, RetranslateStatus } from '@/lib/types'

// ─── Translation ─────────────────────────────────────────────────────────────

export async function translateFile(filePath: string, force = false) {
  const { data } = await api.post('/translate', { file_path: filePath, force })
  return data
}

export async function translateSync(filePath: string, force = false) {
  const { data } = await api.post('/translate/sync', { file_path: filePath, force })
  return data
}

export async function disableTranslation(): Promise<{ status: string; cancelled_jobs: number }> {
  const { data } = await api.post('/translate/disable')
  return data
}

// ─── Translation Backends ────────────────────────────────────────────────────

export async function getBackends(): Promise<{ backends: TranslationBackendInfo[] }> {
  const { data } = await api.get('/backends')
  return data
}

export async function testBackend(name: string): Promise<BackendHealthResult> {
  const { data } = await api.post(`/backends/test/${name}`)
  return data
}

export async function getBackendConfig(name: string): Promise<BackendConfig> {
  const { data } = await api.get(`/backends/${name}/config`)
  return data
}

export async function saveBackendConfig(name: string, config: BackendConfig): Promise<void> {
  await api.put(`/backends/${name}/config`, config)
}

export async function getBackendStats(): Promise<{ stats: BackendStats[] }> {
  const { data } = await api.get('/backends/stats')
  return data
}

export async function ollamaPullModel(model: string): Promise<{ status: string; message?: string }> {
  const { data } = await api.post('/backends/ollama/pull', { model })
  return data
}

// --- Phase 28-01: LLM Backend Presets ---

export interface BackendTemplate {
  name: string
  display_name: string
  backend_type: string
  description: string
  config_defaults: Record<string, unknown>
}

export async function getBackendTemplates(): Promise<{ templates: BackendTemplate[] }> {
  const response = await api.get('/backends/templates')
  return response.data
}

// --- Phase 20-02: Translation Memory ---

export interface TranslationMemoryStats {
  entries: number
  cache_size_bytes?: number
}

export async function getTranslationMemoryStats(): Promise<TranslationMemoryStats> {
  const { data } = await api.get('/translation-memory/stats')
  return data
}

export async function clearTranslationMemoryCache(): Promise<{ cleared: boolean; deleted: number }> {
  const { data } = await api.delete('/translation-memory/cache')
  return data
}

// ─── Re-Translation ──────────────────────────────────────────────────────────

export async function getRetranslateStatus(): Promise<RetranslateStatus> {
  const { data } = await api.get('/retranslate/status')
  return data
}

export async function retranslateSingle(itemId: number): Promise<{ status: string; job_id: string }> {
  const { data } = await api.post(`/retranslate/${itemId}`)
  return data
}

export async function retranslateBatch(): Promise<{ status: string; total: number }> {
  const { data } = await api.post('/retranslate/batch')
  return data
}

// ─── Glossary ─────────────────────────────────────────────────────────────────

export interface GlossaryEntry {
  id: number
  series_id: number | null
  source_term: string
  target_term: string
  notes: string
  term_type: 'character' | 'place' | 'other'
  confidence: number | null
  approved: number  // 0 or 1 (SQLite boolean)
  created_at: string
  updated_at: string
}

export interface GlossaryCandidate {
  source_term: string
  term_type: 'character' | 'place' | 'other'
  frequency: number
  confidence: number
}

export async function getGlossaryEntries(seriesId?: number | null, query?: string): Promise<{ entries: GlossaryEntry[]; series_id: number | null }> {
  const params: Record<string, unknown> = {}
  if (seriesId != null) params.series_id = seriesId
  if (query) params.query = query
  const { data } = await api.get('/glossary', { params })
  return data
}

export async function createGlossaryEntry(entry: { series_id?: number | null; source_term: string; target_term: string; notes?: string; term_type?: 'character' | 'place' | 'other'; confidence?: number | null; approved?: number }): Promise<GlossaryEntry> {
  const { data } = await api.post('/glossary', entry)
  return data
}

export async function updateGlossaryEntry(entryId: number, entry: { source_term?: string; target_term?: string; notes?: string; term_type?: 'character' | 'place' | 'other'; confidence?: number | null; approved?: number }): Promise<GlossaryEntry> {
  const { data } = await api.put(`/glossary/${entryId}`, entry)
  return data
}

export async function deleteGlossaryEntry(entryId: number): Promise<void> {
  await api.delete(`/glossary/${entryId}`)
}

export async function suggestGlossaryTerms(
  seriesId: number,
  options?: { source_lang?: string; min_freq?: number }
): Promise<{ candidates: GlossaryCandidate[]; series_id: number }> {
  const { data } = await api.post(`/series/${seriesId}/glossary/suggest`, options ?? {})
  return data
}

export async function exportGlossaryTsv(seriesId?: number | null): Promise<Blob> {
  const params: Record<string, unknown> = {}
  if (seriesId != null) params.series_id = seriesId
  const { data } = await api.get('/glossary/export', {
    params,
    responseType: 'blob',
  })
  return data
}

// ─── Prompt Presets ───────────────────────────────────────────────────────────

export interface PromptPreset {
  id: number
  name: string
  prompt_template: string
  is_default: number
  created_at: string
  updated_at: string
}

export async function getPromptPresets(): Promise<{ presets: PromptPreset[] }> {
  const { data } = await api.get('/prompt-presets')
  return data
}

export async function getDefaultPromptPreset(): Promise<PromptPreset> {
  const { data } = await api.get('/prompt-presets/default')
  return data
}

export async function createPromptPreset(preset: { name: string; prompt_template: string; is_default?: boolean }): Promise<PromptPreset> {
  const { data } = await api.post('/prompt-presets', preset)
  return data
}

export async function updatePromptPreset(presetId: number, preset: { name?: string; prompt_template?: string; is_default?: boolean }): Promise<PromptPreset> {
  const { data } = await api.put(`/prompt-presets/${presetId}`, preset)
  return data
}

export async function deletePromptPreset(presetId: number): Promise<void> {
  await api.delete(`/prompt-presets/${presetId}`)
}
