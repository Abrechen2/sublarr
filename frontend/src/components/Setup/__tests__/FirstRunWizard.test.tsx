import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FirstRunWizard, { shouldShowWizard, WIZARD_POSTPONED_KEY } from '../FirstRunWizard'
import type { SetupStatus } from '@/api/health'

const mockUseSetupStatus = vi.fn()
const mockUseCompleteSetup = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useSetupStatus: () => mockUseSetupStatus(),
  useCompleteSetup: () => mockUseCompleteSetup(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (!opts) return key
      const parts = Object.entries(opts)
        .map(([k, v]) => `${k}=${String(v)}`)
        .join(',')
      return `${key}:${parts}`
    },
  }),
}))

const SAMPLE_STATUS: SetupStatus = {
  wizard_completed: false,
  benchmark: {
    cpu_count: 8,
    ram_gb: 16,
    recommended_profile: 'balanced',
  },
}

function setup(
  statusOverrides: Partial<SetupStatus> = {},
  mutateImpl?: (profile: string, opts: { onSuccess: (r: unknown) => void }) => void,
) {
  const mutate = vi.fn(
    mutateImpl ??
      ((_profile: string, opts: { onSuccess: (r: unknown) => void }) => {
        opts.onSuccess({ ok: true, profile: _profile, applied: { a: 1, b: 2 } })
      }),
  )
  mockUseSetupStatus.mockReturnValue({
    data: { ...SAMPLE_STATUS, ...statusOverrides, benchmark: { ...SAMPLE_STATUS.benchmark, ...(statusOverrides.benchmark ?? {}) } },
    isLoading: false,
    error: null,
  })
  mockUseCompleteSetup.mockReturnValue({ mutate, isPending: false })
  const onClose = vi.fn()
  const view = render(<FirstRunWizard onClose={onClose} />)
  return { ...view, onClose, mutate }
}

beforeEach(() => {
  mockUseSetupStatus.mockReset()
  mockUseCompleteSetup.mockReset()
  localStorage.clear()
})

describe('FirstRunWizard', () => {
  it('starts on the welcome step', () => {
    setup()
    expect(screen.getByText('welcome.title')).toBeInTheDocument()
    expect(screen.getByTestId('wizard-next')).toBeInTheDocument()
  })

  it('advances to the profile step when Next is clicked', () => {
    setup()
    fireEvent.click(screen.getByTestId('wizard-next'))
    expect(screen.getByText('profile.title')).toBeInTheDocument()
    expect(screen.getByTestId('wizard-profile-balanced')).toBeInTheDocument()
  })

  it('shows the recommended badge on the recommended profile card', () => {
    setup({ benchmark: { cpu_count: 4, ram_gb: 8, recommended_profile: 'light' } })
    fireEvent.click(screen.getByTestId('wizard-next'))
    expect(screen.getByTestId('wizard-recommended-light')).toBeInTheDocument()
    expect(screen.queryByTestId('wizard-recommended-balanced')).not.toBeInTheDocument()
    expect(screen.queryByTestId('wizard-recommended-aggressive')).not.toBeInTheDocument()
  })

  it('calls completeSetup with the picked profile', () => {
    const { mutate } = setup()
    fireEvent.click(screen.getByTestId('wizard-next'))
    fireEvent.click(screen.getByTestId('wizard-profile-light'))
    fireEvent.click(screen.getByTestId('wizard-pick'))
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0][0]).toBe('light')
  })

  it('shows the done step after a successful apply', () => {
    setup()
    fireEvent.click(screen.getByTestId('wizard-next'))
    fireEvent.click(screen.getByTestId('wizard-pick'))
    expect(screen.getByText('done.title')).toBeInTheDocument()
    expect(screen.getByTestId('wizard-done-close')).toBeInTheDocument()
  })

  it('postponing writes a localStorage timestamp and calls onClose', () => {
    const before = Date.now()
    const { onClose } = setup()
    fireEvent.click(screen.getByTestId('wizard-postpone'))
    const stored = localStorage.getItem(WIZARD_POSTPONED_KEY)
    expect(stored).not.toBeNull()
    expect(Number(stored)).toBeGreaterThanOrEqual(before)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('shouldShowWizard', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns false when status is undefined', () => {
    expect(shouldShowWizard(undefined)).toBe(false)
  })

  it('returns false when wizard is already completed', () => {
    expect(shouldShowWizard({ wizard_completed: true })).toBe(false)
  })

  it('returns true on a fresh install', () => {
    expect(shouldShowWizard({ wizard_completed: false })).toBe(true)
  })

  it('returns false during the 7-day postpone window', () => {
    const now = 1_000_000_000_000
    localStorage.setItem(WIZARD_POSTPONED_KEY, String(now - 60_000))
    expect(shouldShowWizard({ wizard_completed: false }, now)).toBe(false)
  })

  it('returns true once the postpone window expires', () => {
    const now = 1_000_000_000_000
    const eightDaysAgo = now - 8 * 24 * 60 * 60 * 1000
    localStorage.setItem(WIZARD_POSTPONED_KEY, String(eightDaysAgo))
    expect(shouldShowWizard({ wizard_completed: false }, now)).toBe(true)
  })
})
