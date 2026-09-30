import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SubtitleDiff from '../SubtitleDiff'

// A plain function, not vi.fn(): a spy tracks the promise it returns and
// reports a rejection the component handles as unhandled.
let applyCalls: unknown[][] = []
let applyResult: () => Promise<unknown> = async () => ({ status: 'applied' })
const applySubtitleDiff = (...args: unknown[]) => {
  applyCalls.push(args)
  return applyResult()
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('../../../api/client', () => ({
  computeSubtitleDiff: vi.fn().mockResolvedValue({
    diffs: [
      {
        type: 'modified',
        original: { start: 1, end: 3, text: 'Hello' },
        modified: { start: 1, end: 3, text: 'Hallo' },
      },
    ],
    total: 1,
    changed: 1,
  }),
  applySubtitleDiff: (...args: unknown[]) => applySubtitleDiff(...args),
}))

vi.mock('../../../hooks/useApi', () => ({
  useSubtitleBackup: () => ({ data: { content: 'backup' }, isLoading: false }),
}))

function renderDiff() {
  render(
    <SubtitleDiff filePath="/media/ep.ass" currentContent="current" lastModified={1234.5} format="ass" />,
  )
}

async function clickApply() {
  const button = await screen.findByText('subtitle_diff.apply_changes')
  fireEvent.click(button)
}

describe('SubtitleDiff apply', () => {
  beforeEach(() => {
    applyCalls = []
    applyResult = async () => ({ status: 'applied' })
  })

  it('sends the last_modified the file was loaded with', async () => {
    renderDiff()

    await clickApply()

    await waitFor(() => expect(applyCalls).toHaveLength(1))
    expect(applyCalls[0][4]).toBe(1234.5)
  })

  it('names the conflict when the file changed since loading', async () => {
    // The shape applySubtitleDiff throws: an Error wrapping the axios error.
    applyResult = async () => {
      throw new Error('File has been modified', { cause: { response: { status: 409 } } })
    }
    renderDiff()

    await clickApply()

    expect(await screen.findByText('subtitle_diff.apply_conflict')).toBeTruthy()
  })
})
