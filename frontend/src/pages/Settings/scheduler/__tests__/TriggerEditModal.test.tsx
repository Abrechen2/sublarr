import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TriggerEditModal } from '../TriggerEditModal'
import type { SchedulerJob } from '@/lib/types'

// i18n mock — match the pattern used in SchedulerPage.test.tsx
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return String(opts.defaultValue ?? k)
      }
      return k
    },
  }),
}))

const makeJob = (trigger: SchedulerJob['trigger']): SchedulerJob => ({
  id: 'test_job',
  description: '',
  owner_module: '',
  trigger,
  trigger_is_default: true,
  paused: false,
  next_run_time: null,
  last_run: null,
  stats_7d: { ok: 0, error: 0, timeout: 0, missed: 0, skipped_overlap: 0 },
})

describe('TriggerEditModal', () => {
  it('does not render when open=false', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open={false}
        onClose={() => {}}
        onSubmit={vi.fn()}
      />,
    )
    expect(screen.queryByText(/scheduler\.edit_trigger_for/)).not.toBeInTheDocument()
  })

  it('pre-selects interval tab when trigger is interval', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={() => {}}
        onSubmit={vi.fn()}
      />,
    )
    // Interval tab active: IntervalEditor renders number input
    const spinbuttons = screen.getAllByRole('spinbutton')
    expect(spinbuttons.length).toBeGreaterThanOrEqual(1)
  })

  it('pre-selects cron tab when trigger is cron', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'cron', hour: '3', minute: '0' })}
        open
        onClose={() => {}}
        onSubmit={vi.fn()}
      />,
    )
    // Cron mode buttons visible (daily/weekly/advanced)
    expect(screen.getByText('scheduler.cron_mode_daily')).toBeInTheDocument()
  })

  it('submits trigger payload on Save click', () => {
    const onSubmit = vi.fn()
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={() => {}}
        onSubmit={onSubmit}
      />,
    )
    // Save button uses defaultValue 'Save' via the i18n mock
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'interval' }),
    )
  })

  it('calls onClose when Cancel clicked', () => {
    const onClose = vi.fn()
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={onClose}
        onSubmit={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('shows error banner when error prop is provided', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={() => {}}
        onSubmit={vi.fn()}
        error="Invalid trigger"
      />,
    )
    expect(screen.getByText('Invalid trigger')).toBeInTheDocument()
  })

  it('disables Save while isSubmitting', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={() => {}}
        onSubmit={vi.fn()}
        isSubmitting
      />,
    )
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
  })
})
