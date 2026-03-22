import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, it, expect, describe } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const mockHooks = [{ id: 1, name: 'Test Hook', event_name: 'subtitle_found', script_path: '/scripts/test.sh', enabled: true, hook_type: 'script', timeout_seconds: 30, last_triggered_at: '', last_status: '', trigger_count: 0, created_at: '', updated_at: '' }]
const mockCreate = vi.fn()
const mockDelete = vi.fn()
const mockUpdate = vi.fn()
const mockTest = vi.fn()
const mockClear = vi.fn()

vi.mock('@/hooks/useIntegrationApi', () => ({
  useHookConfigs: () => ({ data: mockHooks }),
  useCreateHook: () => ({ mutate: mockCreate, isPending: false }),
  useUpdateHook: () => ({ mutate: mockUpdate, isPending: false }),
  useDeleteHook: () => ({ mutate: mockDelete, isPending: false }),
  useTestHook: () => ({ mutate: mockTest, isPending: false }),
  useHookLogs: () => ({ data: [] }),
  useClearHookLogs: () => ({ mutate: mockClear, isPending: false }),
  useEventCatalog: () => ({ data: [{ name: 'subtitle_found' }] }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_: string, fallback?: string) => fallback ?? _ }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const { HooksPage } = await import('../HooksPage')

function renderPage() {
  return render(
    <MemoryRouter>
      <HooksPage />
    </MemoryRouter>
  )
}

describe('HooksPage', () => {
  it('renders hooks list', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Test Hook')).toBeInTheDocument())
  })

  it('opens new hook modal on "New Hook" button click', async () => {
    renderPage()
    fireEvent.click(screen.getByTestId('new-hook-btn'))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
  })

  it('shows confirm dialog on delete', async () => {
    renderPage()
    await waitFor(() => screen.getByText('Test Hook'))
    fireEvent.click(screen.getAllByTestId(`delete-hook-1`)[0])
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders hook logs section', () => {
    renderPage()
    expect(screen.getByTestId('section-hook-logs')).toBeInTheDocument()
  })
})
