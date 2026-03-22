/**
 * StandaloneSettingsTab.test.tsx — Tests for Standalone Mode settings tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StandaloneSettingsTab } from '../StandaloneSettingsTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

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
