import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelJob, purgeMemory, setConcurrency } from '@/api/translation'

/**
 * Phase A1/A2 translation mutations for the cost/memory admin page, the
 * backend-card concurrency slider, and the queue dashboard cancel action.
 * Each mutation invalidates the relevant query group on success so dashboards
 * refresh immediately.
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
    cancelJob: useMutation({
      mutationFn: (jobId: string) => cancelJob(jobId),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['translation', 'queue'] })
      },
    }),
  }
}
