import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getProviders, testProvider, getProviderStats, clearProviderCache,
  getScoringWeights, updateScoringWeights, resetScoringWeights,
  getProviderModifiers, updateProviderModifiers,
  getScoringPresets, importScoringPreset,
  getBlacklist, addToBlacklist, removeFromBlacklist, clearBlacklist,
  getLanguageProfiles, createLanguageProfile, updateLanguageProfile,
  deleteLanguageProfile, assignProfile,
  getHistory, getHistoryStats,
  episodeSearch, episodeHistory,
  searchInteractive, searchInteractiveEpisode,
} from '@/api/client'
import type { LanguageProfile } from '@/lib/types'

// ─── Providers ───────────────────────────────────────────────────────────────

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: getProviders,
    staleTime: 5 * 60_000,
  })
}

export function useTestProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => testProvider(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useProviderStats() {
  return useQuery({
    queryKey: ['provider-stats'],
    queryFn: getProviderStats,
  })
}

export function useClearProviderCache() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (providerName?: string) => clearProviderCache(providerName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['provider-stats'] })
    },
  })
}

// ─── Scoring ─────────────────────────────────────────────────────────────────

export function useScoringWeights() {
  return useQuery({ queryKey: ['scoringWeights'], queryFn: getScoringWeights })
}

export function useUpdateScoringWeights() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateScoringWeights,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['scoringWeights'] }) },
  })
}

export function useResetScoringWeights() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: resetScoringWeights,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['scoringWeights'] }) },
  })
}

export function useProviderModifiers() {
  return useQuery({ queryKey: ['providerModifiers'], queryFn: getProviderModifiers })
}

export function useUpdateProviderModifiers() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateProviderModifiers,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['providerModifiers'] }) },
  })
}

export function useScoringPresets() {
  return useQuery({ queryKey: ['scoringPresets'], queryFn: getScoringPresets })
}

export function useImportScoringPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: importScoringPreset,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['scoringWeights'] })
      void qc.invalidateQueries({ queryKey: ['providerModifiers'] })
    },
  })
}

// ─── Blacklist ────────────────────────────────────────────────────────────────

export function useBlacklist(page = 1, perPage = 50) {
  return useQuery({
    queryKey: ['blacklist', page, perPage],
    queryFn: () => getBlacklist(page, perPage),
  })
}

export function useAddToBlacklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      provider_name: string; subtitle_id: string;
      language?: string; file_path?: string; title?: string; reason?: string
    }) => addToBlacklist(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blacklist'] })
    },
  })
}

export function useRemoveFromBlacklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => removeFromBlacklist(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blacklist'] })
    },
  })
}

export function useClearBlacklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => clearBlacklist(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blacklist'] })
    },
  })
}

// ─── Language Profiles ───────────────────────────────────────────────────────

export function useLanguageProfiles() {
  return useQuery({
    queryKey: ['language-profiles'],
    queryFn: getLanguageProfiles,
    staleTime: 5 * 60_000,
  })
}

export function useCreateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Omit<LanguageProfile, 'id' | 'is_default'>) => createLanguageProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<LanguageProfile> }) =>
      updateLanguageProfile(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

export function useDeleteProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteLanguageProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

export function useAssignProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ type, arrId, profileId }: { type: 'series' | 'movie'; arrId: number; profileId: number }) =>
      assignProfile(type, arrId, profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['language-profiles'] })
    },
  })
}

// ─── History ──────────────────────────────────────────────────────────────────

export function useHistory(page = 1, perPage = 50, provider?: string, language?: string) {
  return useQuery({
    queryKey: ['history', page, perPage, provider, language],
    queryFn: () => getHistory(page, perPage, provider, language),
  })
}

export function useHistoryStats() {
  return useQuery({
    queryKey: ['history-stats'],
    queryFn: getHistoryStats,
  })
}

// ─── Episode Search & History ─────────────────────────────────────────────────

export function useEpisodeSearch() {
  return useMutation({
    mutationFn: (episodeId: number) => episodeSearch(episodeId),
  })
}

export function useEpisodeHistory(episodeId: number) {
  return useQuery({
    queryKey: ['episode-history', episodeId],
    queryFn: () => episodeHistory(episodeId),
    enabled: false,
  })
}

// ─── Interactive Search ───────────────────────────────────────────────────────

export function useSearchInteractive(itemId: number | null, enabled = false) {
  return useQuery({
    queryKey: ['interactive-search', 'wanted', itemId],
    queryFn: () => searchInteractive(itemId!),
    enabled: enabled && !!itemId,
    staleTime: 0,
    gcTime: 5 * 60_000,
  })
}

export function useSearchInteractiveEpisode(episodeId: number | null, enabled = false) {
  return useQuery({
    queryKey: ['interactive-search', 'episode', episodeId],
    queryFn: () => searchInteractiveEpisode(episodeId!),
    enabled: enabled && !!episodeId,
    staleTime: 0,
    gcTime: 5 * 60_000,
  })
}

