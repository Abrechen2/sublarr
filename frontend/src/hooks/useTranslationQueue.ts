import { useQuery } from '@tanstack/react-query'
import { getQueue } from '@/api/translation'

/**
 * Phase A2 translation queue dashboard hook. Polls every 3 seconds while
 * mounted to reflect progress and ETA of running translation jobs.
 */
export function useTranslationQueue() {
  return useQuery({
    queryKey: ['translation', 'queue'],
    queryFn: getQueue,
    refetchInterval: 3000,
  })
}
