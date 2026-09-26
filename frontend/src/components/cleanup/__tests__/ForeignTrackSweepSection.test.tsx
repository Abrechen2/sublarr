/**
 * ForeignTrackSweepSection — the foreign-track sweep's pace controls inside the
 * foreign_tracks cleanup card (1.15.0-rc.5, owner request 2026-09-26).
 *
 * The HTTP layer is mocked at the shared axios instance, so the real API
 * functions and react-query hooks run: what is asserted is the request the
 * page would send.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { SchedulerJob, Trigger } from '@/lib/types'
import { ForeignTrackSweepSection } from '../ForeignTrackSweepSection'
import { toast } from '@/components/shared/Toast'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length > 0
        ? `${key}:${JSON.stringify(Object.fromEntries(Object.entries(opts).filter(([k]) => k !== 'ns')))}`
        : key,
  }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const http = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}))
vi.mock('@/api/core', () => ({ api: http, bootstrapApiKey: vi.fn() }))

function job(trigger: Trigger, overrides: Partial<SchedulerJob> = {}): SchedulerJob {
  return {
    id: 'foreign_track_sweep',
    description: '',
    owner_module: 'services.foreign_tracks.sweep',
    trigger,
    trigger_is_default: false,
    paused: false,
    next_run_time: '2026-09-27T01:00:00+02:00',
    last_run: null,
    stats_7d: {} as SchedulerJob['stats_7d'],
    ...overrides,
  }
}

const STATS = {
  files_stripped: 412,
  tracks_removed: 1650,
  bytes_freed_total: 1,
  bytes_freed_30d: 1,
  scan_counts: { pending: 20, clean: 900, affected: 5566, stripped: 412, failed: 3 },
  phase: 'strip',
  paused_reason: 'disk floor',
}

function serve(opts: { trigger?: Trigger; config?: Record<string, unknown>; jobError?: boolean }) {
  http.get.mockImplementation((url: string) => {
    if (url === '/config')
      return Promise.resolve({
        data: {
          foreign_track_sweep_enabled: false,
          foreign_track_sweep_budget_s: 1800,
          remux_backup_retention_days: 7,
          ...opts.config,
        },
      })
    if (url.startsWith('/scheduler/jobs/foreign_track_sweep')) {
      if (opts.jobError) return Promise.reject(new Error('503'))
      return Promise.resolve({ data: job(opts.trigger ?? { type: 'interval', seconds: 21600 }) })
    }
    if (url === '/statistics/foreign-tracks') return Promise.resolve({ data: STATS })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  http.put.mockResolvedValue({ data: { status: 'saved' } })
  http.patch.mockImplementation((_url: string, body: { trigger: Trigger }) =>
    Promise.resolve({ data: job(body.trigger) }),
  )
  http.post.mockResolvedValue({ data: { status: 'queued', oneshot_id: 'x' } })
}

function renderSection(ruleEnabled = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ForeignTrackSweepSection ruleEnabled={ruleEnabled} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function presetSelect(): Promise<HTMLSelectElement> {
  return (await screen.findByTestId('sweep-preset')) as HTMLSelectElement
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ForeignTrackSweepSection — schedule preset', () => {
  it('detects the active preset from the live trigger', async () => {
    serve({ trigger: { type: 'interval', seconds: 3600 } })
    renderSection()
    await waitFor(async () => expect((await presetSelect()).value).toBe('hourly'))
    expect(screen.getByTestId('sweep-next-run').textContent).toContain('cleanup_card.sweep.next_run')
  })

  it('sends the nightly cron in the browser time zone', async () => {
    serve({})
    renderSection()
    const select = await presetSelect()
    await waitFor(() => expect(select.value).toBe('every6h'))
    fireEvent.change(select, { target: { value: 'nightly' } })
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    await waitFor(() =>
      expect(http.patch).toHaveBeenCalledWith('/scheduler/jobs/foreign_track_sweep', {
        trigger: { type: 'cron', hour: '1-6', minute: '0', timezone: tz },
      }),
    )
  })

  it('sends a 1 h interval for hourly', async () => {
    serve({})
    renderSection()
    const select = await presetSelect()
    await waitFor(() => expect(select.value).toBe('every6h'))
    fireEvent.change(select, { target: { value: 'hourly' } })
    await waitFor(() =>
      expect(http.patch).toHaveBeenCalledWith('/scheduler/jobs/foreign_track_sweep', {
        trigger: { type: 'interval', hours: 1 },
      }),
    )
  })

  it('resets to the job default for the 6 h preset instead of patching', async () => {
    serve({ trigger: { type: 'interval', seconds: 3600 } })
    renderSection()
    const select = await presetSelect()
    await waitFor(() => expect(select.value).toBe('hourly'))
    fireEvent.change(select, { target: { value: 'every6h' } })
    await waitFor(() =>
      expect(http.post).toHaveBeenCalledWith('/scheduler/jobs/foreign_track_sweep/reset-default'),
    )
    expect(http.patch).not.toHaveBeenCalled()
  })

  it('shows a foreign trigger as custom, read-only, with a link to the scheduler', async () => {
    serve({ trigger: { type: 'cron', hour: '2', minute: '15', timezone: 'UTC' } })
    renderSection()
    const select = await presetSelect()
    await waitFor(() => expect(select.value).toBe('custom'))
    const link = screen.getByRole('link', { name: 'cleanup_card.sweep.open_scheduler' })
    expect(link.getAttribute('href')).toBe('/settings/system/scheduler')
  })

  it('says so when the scheduler cannot be read', async () => {
    serve({ jobError: true })
    renderSection()
    expect(await screen.findByText('cleanup_card.sweep.scheduler_unavailable')).toBeTruthy()
  })
})

describe('ForeignTrackSweepSection — settings', () => {
  it('toggles foreign_track_sweep_enabled', async () => {
    serve({})
    renderSection()
    const toggle = await screen.findByRole('switch')
    await waitFor(() => expect(toggle.getAttribute('aria-checked')).toBe('false'))
    fireEvent.click(toggle)
    await waitFor(() =>
      expect(http.put).toHaveBeenCalledWith('/config', { foreign_track_sweep_enabled: true }),
    )
  })

  it('saves the budget in seconds, clamped to 60 minutes', async () => {
    serve({})
    renderSection()
    const input = (await screen.findByTestId('sweep-budget')) as HTMLInputElement
    await waitFor(() => expect(input.value).toBe('30'))
    fireEvent.change(input, { target: { value: '120' } })
    fireEvent.blur(input)
    await waitFor(() =>
      expect(http.put).toHaveBeenCalledWith('/config', { foreign_track_sweep_budget_s: 3600 }),
    )
    expect(input.value).toBe('60')
  })

  it('does not save an unchanged budget', async () => {
    serve({})
    renderSection()
    const input = (await screen.findByTestId('sweep-budget')) as HTMLInputElement
    await waitFor(() => expect(input.value).toBe('30'))
    fireEvent.blur(input)
    // A mutation dispatches asynchronously; give it the chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(http.put).not.toHaveBeenCalled()
  })

  it('shows the backup retention read-only with a link to the remux settings', async () => {
    serve({ config: { remux_backup_retention_days: 14 } })
    renderSection()
    expect(await screen.findByText(/cleanup_card\.sweep\.retention_value:\{"count":14\}/)).toBeTruthy()
    const link = screen.getByRole('link', { name: 'cleanup_card.sweep.retention_link' })
    expect(link.getAttribute('href')).toBe('/settings/subtitles/stream-management')
  })
})

describe('ForeignTrackSweepSection — progress and run now', () => {
  it('shows remaining, stripped, phase and paused reason', async () => {
    serve({ config: { foreign_track_sweep_enabled: true } })
    renderSection()
    const line = await screen.findByTestId('sweep-progress')
    const affected = (5566).toLocaleString()
    await waitFor(() => expect(line.textContent).toContain(`"affected":"${affected}"`))
    expect(line.textContent).toContain('"stripped":"412"')
    expect(line.textContent).toContain('track_cleanup.phase.strip')
    expect(line.textContent).toContain('"reason":"disk floor"')
  })

  it('queues a run', async () => {
    serve({ config: { foreign_track_sweep_enabled: true } })
    renderSection()
    const btn = await screen.findByRole('button', { name: /cleanup_card\.sweep\.run_now/ })
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(btn)
    await waitFor(() =>
      expect(http.post).toHaveBeenCalledWith('/scheduler/jobs/foreign_track_sweep/run-now'),
    )
    await waitFor(() => expect(toast).toHaveBeenCalledWith('cleanup_card.sweep.queued', 'success'))
  })

  it('turns a 409 already-pending into a friendly note, not an error', async () => {
    serve({ config: { foreign_track_sweep_enabled: true } })
    http.post.mockRejectedValue({ response: { status: 409 } })
    renderSection()
    const btn = await screen.findByRole('button', { name: /cleanup_card\.sweep\.run_now/ })
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(btn)
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith('cleanup_card.sweep.already_pending', 'info'),
    )
  })

  it('cannot start while the sweep is off', async () => {
    serve({})
    renderSection()
    const btn = await screen.findByRole('button', { name: /cleanup_card\.sweep\.run_now/ })
    expect((btn as HTMLButtonElement).disabled).toBe(true)
  })

  it('warns when the rule itself is inactive', async () => {
    serve({ config: { foreign_track_sweep_enabled: true } })
    renderSection(false)
    expect(await screen.findByText('cleanup_card.sweep.rule_inactive')).toBeTruthy()
  })
})
