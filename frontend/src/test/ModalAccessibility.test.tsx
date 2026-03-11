/**
 * ModalAccessibility.test.tsx — Verify role="dialog" and aria-modal attributes
 * on modal components that were updated in the v0.21.1 UI/UX polish pass.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/hooks/useApi', () => ({
  useGlobalSearch: () => ({ data: undefined, isFetching: false }),
  useProviders: () => ({ data: [] }),
  useLibrary: () => ({ data: [] }),
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => ({}),
}))

describe('Modal accessibility attributes', () => {
  it('GlobalSearchModal has role=dialog and aria-modal when open', async () => {
    const { GlobalSearchModal } = await import('@/components/search/GlobalSearchModal')
    const { container } = render(
      <MemoryRouter>
        <GlobalSearchModal open={true} onOpenChange={() => {}} />
      </MemoryRouter>
    )
    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })
})
