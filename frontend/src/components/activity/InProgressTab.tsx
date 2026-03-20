import { QueuePage } from '@/pages/Queue'

/**
 * InProgressTab — wraps the existing QueuePage content for display
 * inside the unified ActivityPage tabs.
 */
export function InProgressTab() {
  return (
    <div data-testid="in-progress-tab">
      <QueuePage />
    </div>
  )
}
