import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockToast = vi.fn()
const mockClipboardWrite = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      return key
    },
  }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}))

vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div>
      <h2>{title}</h2>
      {children}
    </div>
  ),
}))

vi.mock('@/components/shared/SettingRow', () => ({
  SettingRow: ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div>
      <label>{label}</label>
      {children}
    </div>
  ),
}))

// ─── Tests ───────────────────────────────────────────────────────────────────

import React from 'react'
import { WebhooksSection } from '../connections/WebhooksSection'

function renderSection() {
  return render(<WebhooksSection />)
}

describe('WebhooksSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: mockClipboardWrite.mockResolvedValue(undefined) },
    })
  })

  it('renders webhook URL for sonarr', () => {
    renderSection()
    const el = screen.getByTestId('webhook-url-sonarr')
    expect(el.textContent).toContain('/api/v1/webhook/sonarr')
  })

  it('renders webhook URL for radarr', () => {
    renderSection()
    const el = screen.getByTestId('webhook-url-radarr')
    expect(el.textContent).toContain('/api/v1/webhook/radarr')
  })

  it('renders webhook URL for jellyfin', () => {
    renderSection()
    const el = screen.getByTestId('webhook-url-jellyfin')
    expect(el.textContent).toContain('/api/v1/webhook/jellyfin')
  })

  it('copies URL and shows toast when copy button clicked', () => {
    renderSection()
    fireEvent.click(screen.getByTestId('webhook-copy-sonarr'))
    expect(mockClipboardWrite).toHaveBeenCalledWith(expect.stringContaining('/api/v1/webhook/sonarr'))
    expect(mockToast).toHaveBeenCalledWith('webhooks_page.copied')
  })
})
