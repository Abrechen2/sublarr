/**
 * StandaloneSettingsTab.test.tsx — Tests for Standalone Mode settings tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StandaloneSettingsTab } from '../StandaloneSettingsTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

import enSettings from '../../../i18n/locales/en/settings.json'
import enCommon from '../../../i18n/locales/en/common.json'

function lookupKey(ns: Record<string, unknown>, key: string): string | undefined {
  const parts = key.split('.')
  let v: unknown = ns
  for (const p of parts) {
    if (typeof v !== 'object' || v === null) return undefined
    v = (v as Record<string, unknown>)[p]
  }
  return typeof v === 'string' ? v : undefined
}

vi.mock('react-i18next', () => ({
  useTranslation: (ns?: string) => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      const dict = ns === 'settings' ? enSettings : enCommon
      return lookupKey(dict, key) ?? key
    },
  }),
}))

const mutateMock = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      standalone_scan_interval_hours: '12',
      standalone_debounce_seconds: '60',
      standalone_skip_extras: 'false',
    },
  }),
  useUpdateConfig: () => ({ mutate: mutateMock, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderTab() {
  return render(
    <AdvancedSettingsProvider>
      <StandaloneSettingsTab />
    </AdvancedSettingsProvider>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('StandaloneSettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Scan Interval label', () => {
    renderTab()
    expect(screen.getByText('Scan Interval (hours)')).toBeInTheDocument()
  })

  it('renders Scan Interval input with value from config', () => {
    renderTab()
    const spinners = screen.getAllByRole('spinbutton')
    expect(spinners.some((el) => (el as HTMLInputElement).value === '12')).toBe(true)
  })

  it('renders Debounce label', () => {
    renderTab()
    expect(screen.getByText('Debounce (seconds)')).toBeInTheDocument()
  })

  it('renders Debounce input with value from config', () => {
    renderTab()
    const spinners = screen.getAllByRole('spinbutton')
    expect(spinners.some((el) => (el as HTMLInputElement).value === '60')).toBe(true)
  })

  it('renders Skip Extras toggle', () => {
    renderTab()
    expect(screen.getByText('Skip Extras')).toBeInTheDocument()
  })

  it('calls updateConfig on toggle change', () => {
    renderTab()
    const toggle = screen.getByRole('switch')
    fireEvent.click(toggle)
    expect(mutateMock).toHaveBeenCalled()
  })

  it('calls updateConfig on blur for scan interval', () => {
    renderTab()
    const spinners = screen.getAllByRole('spinbutton')
    const intervalInput = spinners.find((el) => (el as HTMLInputElement).value === '12') as HTMLInputElement
    fireEvent.blur(intervalInput)
    expect(mutateMock).toHaveBeenCalled()
  })
})
