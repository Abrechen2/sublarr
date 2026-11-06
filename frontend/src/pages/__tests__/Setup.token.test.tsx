/**
 * Setup.token.test.tsx — the first setup asks for the logged token when the
 * backend says this client is outside the local network (#72).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SetupPage } from '../Setup'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}))

const setupAuth = vi.fn()
vi.mock('@/api/client', () => ({ setupAuth: (body: unknown) => setupAuth(body) }))
vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SetupPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SetupPage setup token', () => {
  beforeEach(() => setupAuth.mockReset())

  it('shows no token field until the backend asks for one', () => {
    renderPage()
    expect(screen.queryByLabelText('setup.token_label')).toBeNull()
  })

  it('asks for the token after a 403 and sends it on the next try', async () => {
    setupAuth.mockRejectedValueOnce({ response: { data: { setup_token_required: true } } })
    setupAuth.mockResolvedValueOnce(undefined)
    renderPage()

    fireEvent.click(screen.getByText('setup.continue_open'))
    const field = await screen.findByLabelText('setup.token_label')
    expect(setupAuth).toHaveBeenLastCalledWith({ action: 'disable' })

    fireEvent.change(field, { target: { value: '  tok-123 ' } })
    fireEvent.click(screen.getByText('setup.continue_open'))
    await waitFor(() =>
      expect(setupAuth).toHaveBeenLastCalledWith({ action: 'disable', setup_token: 'tok-123' }),
    )
  })
})
