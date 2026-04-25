import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getScopesTree, getResolved, patchOverride, resetOverrides,
  type ScopesTree, type ResolvedSettings,
} from '@/api/profilesOverrides'

export function useScopesTree() {
  return useQuery<ScopesTree>({
    queryKey: ['profiles-overrides', 'scopes'],
    queryFn: getScopesTree,
    staleTime: 30_000,
  })
}

export function useResolved(
  scopeType: 'global' | 'profile' | 'series' | 'movie',
  scopeId: number | null,
) {
  return useQuery<ResolvedSettings>({
    queryKey: ['profiles-overrides', 'resolved', scopeType, scopeId],
    queryFn: () => getResolved(scopeType, scopeId ?? undefined),
    enabled: scopeType === 'global' || scopeId !== null,
    staleTime: 0,
  })
}

export function useOverrideMutation(
  scopeType: 'series' | 'movie',
  scopeId: number,
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => patchOverride(scopeType, scopeId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['profiles-overrides', 'resolved', scopeType, scopeId] })
      void qc.invalidateQueries({ queryKey: ['profiles-overrides', 'scopes'] })
    },
  })
}

export function useResetMutation(scopeType: 'series' | 'movie', scopeId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => resetOverrides(scopeType, scopeId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['profiles-overrides', 'resolved', scopeType, scopeId] })
    },
  })
}
