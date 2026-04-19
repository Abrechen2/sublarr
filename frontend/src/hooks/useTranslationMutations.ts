import { useMutation, useQueryClient } from '@tanstack/react-query'
import { purgeMemory, setConcurrency } from '@/api/translation'

/**
 * Phase A1 translation mutations for the cost/memory admin page and the
 * backend-card concurrency slider. Each mutation invalidates the relevant
 * query group on success so dashboards refresh immediately.
 */
export function useTranslationMutations() {
  const qc = useQueryClient()
  return {
    purgeMemory: useMutation({
      mutationFn: (params: { older_than_days?: number; backend?: string }) =>
        purgeMemory(params),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['translation', 'memory'] })
      },
    }),
    setConcurrency: useMutation({
      mutationFn: ({ backend, limit }: { backend: string; limit: number }) =>
        setConcurrency(backend, limit),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['translation', 'concurrency'] })
      },
    }),
  }
}
