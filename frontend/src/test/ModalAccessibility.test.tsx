/**
 * ModalAccessibility.test.tsx — Verify role="dialog" and aria-modal attributes
 * on modal components that were updated in the v0.21.1 UI/UX polish pass.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { WidgetSettingsModal } from '@/components/dashboard/WidgetSettingsModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/stores/dashboardStore', () => ({
  useDashboardStore: (selector: (s: { hiddenWidgets: string[]; toggleWidget: () => void; resetToDefault: () => void }) => unknown) =>
    selector({ hiddenWidgets: [], toggleWidget: vi.fn(), resetToDefault: vi.fn() }),
}))

describe('Modal accessibility attributes', () => {
  it('WidgetSettingsModal has role=dialog and aria-modal when open', () => {
    const { container } = render(
      <WidgetSettingsModal open={true} onClose={() => {}} />
    )
    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })
})
