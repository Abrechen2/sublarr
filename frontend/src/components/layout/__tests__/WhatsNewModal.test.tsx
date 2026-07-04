import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WhatsNewModal } from '../WhatsNewModal'
import { versionKey, WHATS_NEW } from '@/content/whatsNew'

import { vi } from 'vitest'
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

describe('versionKey', () => {
  it('normalises a pre-release version to the content key', () => {
    expect(versionKey('1.6.0-beta')).toBe('1.6.0')
    expect(versionKey('v1.6.0')).toBe('1.6.0')
    expect(versionKey('1.6.0')).toBe('1.6.0')
  })
  it('returns null when no content exists for the version', () => {
    expect(versionKey('1.5.0')).toBeNull()
    expect(versionKey(undefined)).toBeNull()
  })
})

describe('WhatsNewModal', () => {
  it('renders a highlight per item for the version', () => {
    render(<WhatsNewModal open version="1.6.0" onDismiss={() => {}} />)
    const items = WHATS_NEW['1.6.0']
    for (const item of items) {
      expect(screen.getByText(item.titleKey)).toBeInTheDocument()
    }
  })

  it('renders nothing when closed or version is null', () => {
    const { container, rerender } = render(<WhatsNewModal open={false} version="1.6.0" onDismiss={() => {}} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<WhatsNewModal open version={null} onDismiss={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
