import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CombineDialog } from '../CombineDialog'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const combineMock = vi.fn()
vi.mock('@/api/library', () => ({
  combineEpisodeSubtitles: (...args: unknown[]) => combineMock(...args),
}))

function renderDialog(extra: Partial<React.ComponentProps<typeof CombineDialog>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <CombineDialog
        open
        episodeId={7}
        episodeTitle="Show — S01E01"
        availableLanguages={['de', 'en']}
        targetLanguages={['de', 'en']}
        seriesId={3}
        onClose={vi.fn()}
        {...extra}
      />
    </QueryClientProvider>,
  )
}

describe('CombineDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not render when closed', () => {
    const { container } = renderDialog({ open: false })
    expect(container).toBeEmptyDOMElement()
  })

  it('submits the selected languages, format and translate flag', async () => {
    combineMock.mockResolvedValue({ combined_path: '/x.de-en.combined.ass' })
    renderDialog()

    fireEvent.click(screen.getByText('combine_dialog.combine'))

    await waitFor(() => expect(combineMock).toHaveBeenCalledTimes(1))
    expect(combineMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        languages: ['de', 'en'],
        format: 'ass',
        translate_missing: false,
      }),
    )
  })

  it('sends translate_missing=true when the toggle is checked', async () => {
    combineMock.mockResolvedValue({ combined_path: '/x' })
    renderDialog()

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('combine_dialog.combine'))

    await waitFor(() => expect(combineMock).toHaveBeenCalled())
    expect(combineMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ translate_missing: true }),
    )
  })
})
