import { z } from 'zod'
import { api } from './client'

// ─── Schemas ────────────────────────────────────────────────────────────────
const ScopeKindSchema = z.enum(['global', 'profile', 'series', 'movie'])

const ChainStepSchema = z.object({
  scope: ScopeKindSchema,
  value: z.unknown(),
  label: z.string(),
})

const ResolvedSettingSchema = z.object({
  effective: z.unknown(),
  source: ScopeKindSchema,
  chain: z.array(ChainStepSchema),
})

export const ResolvedSettingsSchema = z.object({
  scope: z.object({
    type: ScopeKindSchema,
    id: z.number().nullable(),
    name: z.string(),
  }),
  settings: z.record(z.string(), ResolvedSettingSchema),
})

const ProfileTreeNodeSchema = z.object({
  id: z.number(),
  name: z.string(),
  is_default: z.boolean(),
  series: z.array(z.object({ id: z.number(), title: z.string() })),
  movies: z.array(z.object({ id: z.number(), title: z.string() })),
})

export const ScopesTreeSchema = z.object({
  profiles: z.array(ProfileTreeNodeSchema),
  unassigned_series: z.array(z.object({ id: z.number(), title: z.string() })),
  unassigned_movies: z.array(z.object({ id: z.number(), title: z.string() })),
})

export type ScopesTree = z.infer<typeof ScopesTreeSchema>
export type ResolvedSettings = z.infer<typeof ResolvedSettingsSchema>
export type ResolvedSetting = z.infer<typeof ResolvedSettingSchema>
export type ChainStep = z.infer<typeof ChainStepSchema>

// ─── HTTP functions ─────────────────────────────────────────────────────────
const BASE = '/profiles-overrides'

export async function getScopesTree(): Promise<ScopesTree> {
  const { data } = await api.get(`${BASE}/scopes`)
  return ScopesTreeSchema.parse(data)
}

export async function getResolved(
  scopeType: 'global' | 'profile' | 'series' | 'movie',
  scopeId?: number,
): Promise<ResolvedSettings> {
  const url =
    scopeType === 'global'
      ? `${BASE}/resolved/global`
      : `${BASE}/resolved/${scopeType}/${scopeId}`
  const { data } = await api.get(url)
  return ResolvedSettingsSchema.parse(data)
}

export async function patchOverride(
  scopeType: 'series' | 'movie',
  scopeId: number,
  body: Record<string, unknown>,
): Promise<{ ok: boolean }> {
  const { data } = await api.patch(`${BASE}/${scopeType}/${scopeId}`, body)
  return data
}

export async function resetOverrides(
  scopeType: 'series' | 'movie',
  scopeId: number,
): Promise<{ ok: boolean }> {
  const { data } = await api.post(`${BASE}/${scopeType}/${scopeId}/reset`, {})
  return data
}

export async function createSeriesOverride(seriesId: number): Promise<{ created: boolean }> {
  const { data } = await api.post(`${BASE}/series/${seriesId}/create-override`, {})
  return data
}

export async function createMovieOverride(movieId: number): Promise<{ created: boolean }> {
  const { data } = await api.post(`${BASE}/movie/${movieId}/create-override`, {})
  return data
}

export async function deleteSeriesScope(seriesId: number): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`${BASE}/series/${seriesId}`)
  return data
}

export async function deleteMovieScope(movieId: number): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`${BASE}/movie/${movieId}`)
  return data
}
