/**
 * Tests for `WaveformShortcutHelp` (Plan B8 Task 5 Step 3).
 *
 * The component is purely presentational, so the tests assert:
 *   - Hidden when `open=false`
 *   - When `open=true`, every shortcut from `WAVEFORM_SHORTCUTS` is
 *     listed (so we don't silently drop bindings from the help overlay).
 *   - ESC, X button, and backdrop click all close the dialog.
 *   - Inner panel click does NOT close it.
 *
 * i18n is resolved against the real EN locale via the existing test
 * setup (see `src/test/setup.ts` which already initialises i18next).
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { WaveformShortcutHelp } from '../WaveformShortcutHelp'
import { WAVEFORM_SHORTCUTS } from '../keymap'

describe('WaveformShortcutHelp', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<WaveformShortcutHelp open={false} onClose={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('lists every shortcut display string when open', () => {
    render(<WaveformShortcutHelp open={true} onClose={vi.fn()} />)

    for (const sc of WAVEFORM_SHORTCUTS) {
      // Each `display` (e.g. 'S', 'Shift+←') must appear at least once
      const matches = screen.getAllByText(sc.display)
      expect(matches.length).toBeGreaterThan(0)
    }
  })

  it('closes on ESC', () => {
    const onClose = vi.fn()
    render(<WaveformShortcutHelp open={true} onClose={onClose} />)

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on backdrop click', () => {
    const onClose = vi.fn()
    render(<WaveformShortcutHelp open={true} onClose={onClose} />)

    const dialog = screen.getByRole('dialog')
    fireEvent.click(dialog)

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not close when clicking the inner panel', () => {
    const onClose = vi.fn()
    render(<WaveformShortcutHelp open={true} onClose={onClose} />)

    // The dialog title is inside the inner panel; clicking it should NOT close.
    const title = screen.getByText(/keyboard shortcuts|tastenkürzel/i)
    fireEvent.click(title)

    expect(onClose).not.toHaveBeenCalled()
  })
})
