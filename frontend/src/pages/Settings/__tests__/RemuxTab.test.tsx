/**
 * RemuxTab.test.tsx — Tests for Remux settings tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RemuxTab } from '../RemuxTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mutateMock = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      remux_trash_dir: '/media/trash',
      remux_backup_retention_days: '7',
      remux_use_reflink: 'false',
      remux_arr_pause_enabled: 'true',
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
      <RemuxTab />
    </AdvancedSettingsProvider>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('RemuxTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Trash Directory label', () => {
    renderTab()
    expect(screen.getByText('Trash Directory')).toBeInTheDocument()
  })

  it('renders Trash Directory input with value from config', () => {
    renderTab()
    const inputs = screen.getAllByRole('textbox')
    expect(inputs.some((el) => (el as HTMLInputElement).value === '/media/trash')).toBe(true)
  })

  it('renders Backup Retention days input', () => {
    renderTab()
    expect(screen.getByText('Backup Retention (days)')).toBeInTheDocument()
    const spinners = screen.getAllByRole('spinbutton')
    expect(spinners.some((el) => (el as HTMLInputElement).value === '7')).toBe(true)
  })

  it('renders Use Reflink toggle', () => {
    renderTab()
    expect(screen.getByText('Use Reflink')).toBeInTheDocument()
  })

  it('renders Pause Arr on Remux toggle', () => {
    renderTab()
    expect(screen.getByText('Pause Arr on Remux')).toBeInTheDocument()
  })

  it('calls updateConfig on toggle change', () => {
    renderTab()
    const toggles = screen.getAllByRole('switch')
    fireEvent.click(toggles[0])
    expect(mutateMock).toHaveBeenCalled()
  })

  it('calls updateConfig on blur for trash dir', () => {
    renderTab()
    const inputs = screen.getAllByRole('textbox')
    const trashInput = inputs.find((el) => (el as HTMLInputElement).value === '/media/trash') as HTMLInputElement
    fireEvent.blur(trashInput)
    expect(mutateMock).toHaveBeenCalled()
  })
})
