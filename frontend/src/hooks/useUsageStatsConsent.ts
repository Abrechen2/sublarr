import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getUsageStatsConsent, setUsageStatsConsent } from '@/api/system/usageStats'

export function useUsageStatsConsent() {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: ['usage-stats-consent'], queryFn: getUsageStatsConsent })
  const mutation = useMutation({
    mutationFn: setUsageStatsConsent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['usage-stats-consent'] }),
  })
  return {
    consent: query.data?.consent ?? 'unset',
    isLoading: query.isLoading,
    setConsent: mutation.mutate,
  }
}
