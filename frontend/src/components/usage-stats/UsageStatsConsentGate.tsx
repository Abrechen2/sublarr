import { useUsageStatsConsent } from '@/hooks/useUsageStatsConsent'
import { UsageStatsConsentCard } from './UsageStatsConsentCard'

/**
 * App-level catch-all: shows the consent card in a modal whenever consent is
 * still `unset`, so every install (new or existing) is asked exactly once —
 * independent of onboarding/What's-New firing. `enabled` is gated by the caller
 * so it never stacks on the first-run wizard, the What's-New modal, or auth
 * routes. Choosing sets consent, which flips this to `unset === false` and the
 * modal disappears for good.
 */
export function UsageStatsConsentGate({ enabled }: { enabled: boolean }) {
  const { consent } = useUsageStatsConsent()
  if (!enabled || consent !== 'unset') return null

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      role="dialog"
      aria-modal="true"
      aria-label="Usage statistics consent"
    >
      <div className="w-full max-w-md">
        <UsageStatsConsentCard />
      </div>
    </div>
  )
}
