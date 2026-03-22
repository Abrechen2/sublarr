import { render, screen, fireEvent } from '@testing-library/react'
import { vi, it, expect, describe } from 'vitest'

const mockConvert = vi.fn()

vi.mock('@/hooks/useTranslationApi', () => ({
  useConvertSubtitleFormat: () => ({ mutate: mockConvert, isPending: false }),
}))

const stableContentData = { content: 'test content', last_modified: '2026-01-01', format: 'ass' }

vi.mock('@/hooks/useLibraryApi', () => ({
  useSubtitleContent: () => ({ data: stableContentData }),
}))

vi.mock('@/api/client', () => ({
  autoSyncFile: vi.fn(),
  overlapFix: vi.fn(),
  timingNormalize: vi.fn(),
  mergeLines: vi.fn(),
  splitLines: vi.fn(),
  spellCheck: vi.fn(),
  removeCredits: vi.fn(),
  detectOpeningEnding: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

vi.mock('react-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-dom')>()
  return { ...actual, createPortal: (children: React.ReactNode) => children }
})

vi.mock('@/components/editor/SubtitlePreview', () => ({
  default: () => <div data-testid="subtitle-preview-stub" />,
}))
vi.mock('@/components/editor/SubtitleEditor', () => ({
  SubtitleEditor: () => <div data-testid="subtitle-editor-stub" />,
}))
vi.mock('@/components/editor/SubtitleDiff', () => ({
  default: () => <div data-testid="subtitle-diff-stub" />,
}))
vi.mock('@/components/editor/WaveformTab', () => ({
  WaveformTab: () => <div data-testid="waveform-tab-stub" />,
}))

import SubtitleEditorModal from '../SubtitleEditorModal'

const onClose = vi.fn()

describe('SubtitleEditorModal convert', () => {
  it('renders format select and convert button in edit mode', () => {
    render(<SubtitleEditorModal filePath="/test/subtitle.ass" initialMode="edit" onClose={onClose} />)
    expect(screen.getByTestId('convert-format-select')).toBeInTheDocument()
    expect(screen.getByTestId('convert-format-btn')).toBeInTheDocument()
  })

  it('does not render convert UI in preview mode', () => {
    render(<SubtitleEditorModal filePath="/test/subtitle.ass" initialMode="preview" onClose={onClose} />)
    expect(screen.queryByTestId('convert-format-select')).not.toBeInTheDocument()
  })

  it('calls convertMut with correct target format on convert button click', () => {
    render(<SubtitleEditorModal filePath="/test/subtitle.ass" initialMode="edit" onClose={onClose} />)
    // Select VTT format then click convert
    const select = screen.getByTestId('convert-format-select')
    fireEvent.change(select, { target: { value: 'vtt' } })
    // Click convert
    fireEvent.click(screen.getByTestId('convert-format-btn'))
    expect(mockConvert).toHaveBeenCalledWith(
      { filePath: '/test/subtitle.ass', targetFormat: 'vtt' },
      expect.any(Object)
    )
  })
})
