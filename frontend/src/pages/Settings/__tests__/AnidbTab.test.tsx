/**
 * AnidbTab.test.tsx — Tests for AniDB settings tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AnidbTab } from '../AnidbTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}))

const mutateMock = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      anidb_enabled: 'false',
      anidb_cache_ttl_days: '7',
      anidb_custom_field_name: 'anidb_id',
      anidb_fallback_to_mapping: 'true',
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
      <AnidbTab />
    </AdvancedSettingsProvider>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('AnidbTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Enable AniDB toggle', () => {
    renderTab()
    expect(screen.getByText('anidb_tab.enable')).toBeInTheDocument()
  })

  it('renders Cache TTL number input', () => {
    renderTab()
    expect(screen.getByText('anidb_tab.cache_ttl')).toBeInTheDocument()
    const spinners = screen.getAllByRole('spinbutton')
    expect(spinners.some((el) => (el as HTMLInputElement).value === '7')).toBe(true)
  })

  it('renders Custom Field Name text input', () => {
    renderTab()
    expect(screen.getByText('anidb_tab.custom_field')).toBeInTheDocument()
    const inputs = screen.getAllByRole('textbox')
    expect(inputs.some((el) => (el as HTMLInputElement).value === 'anidb_id')).toBe(true)
  })

  it('renders Fallback to Mapping toggle', () => {
    renderTab()
    expect(screen.getByText('anidb_tab.fallback_mapping')).toBeInTheDocument()
  })

  it('calls updateConfig immediately when toggle changes', () => {
    renderTab()
    const toggles = screen.getAllByRole('switch')
    fireEvent.click(toggles[0])
    expect(mutateMock).toHaveBeenCalled()
  })

  it('calls updateConfig on blur for cache TTL', () => {
    renderTab()
    const spinners = screen.getAllByRole('spinbutton')
    const ttlInput = spinners.find((el) => (el as HTMLInputElement).value === '7') as HTMLInputElement
    fireEvent.blur(ttlInput)
    expect(mutateMock).toHaveBeenCalled()
  })
})
