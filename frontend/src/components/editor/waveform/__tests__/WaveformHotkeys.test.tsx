/**
 * Tests for `WaveformHotkeys` (Plan B8 Task 5).
 *
 * The component itself only registers `useHotkeys` bindings; the test
 * dispatches synthetic `keydown` events on `document.body` and asserts
 * the dispatcher saw the right action id.
 *
 * Two important behaviours covered:
 *  1. Bindings only fire when `enabled` is true (so the modal can switch
 *     them off without unmounting).
 *  2. Typing inside an `<input>` does NOT hijack the keymap — the
 *     react-hotkeys-hook default (`enableOnFormTags: false`) is what
 *     makes Aegisub-style single-letter shortcuts coexist with text
 *     fields elsewhere in the editor.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { WaveformHotkeys } from '../WaveformHotkeys'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('WaveformHotkeys', () => {
  it('dispatches "setStart" on S keypress', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard('s')

    expect(onAction).toHaveBeenCalledWith('setStart')
  })

  it('dispatches "setEnd" on D keypress', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard('d')

    expect(onAction).toHaveBeenCalledWith('setEnd')
  })

  it('dispatches "playPause" on Space', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard(' ')

    expect(onAction).toHaveBeenCalledWith('playPause')
  })

  it('dispatches "seekBack1s" on Shift+Left', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard('{Shift>}{ArrowLeft}{/Shift}')

    expect(onAction).toHaveBeenCalledWith('seekBack1s')
  })

  it('dispatches "nextDefect" on N and "prevDefect" on Shift+N', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard('n')
    expect(onAction).toHaveBeenCalledWith('nextDefect')

    await userEvent.keyboard('{Shift>}n{/Shift}')
    expect(onAction).toHaveBeenCalledWith('prevDefect')
  })

  it('dispatches keyframe jumps on K and Shift+K', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard('k')
    expect(onAction).toHaveBeenCalledWith('nextKeyframe')

    await userEvent.keyboard('{Shift>}k{/Shift}')
    expect(onAction).toHaveBeenCalledWith('prevKeyframe')
  })

  it('dispatches scene-cut jumps on C and Shift+C', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={true} onAction={onAction} />)

    await userEvent.keyboard('c')
    expect(onAction).toHaveBeenCalledWith('nextScene')

    await userEvent.keyboard('{Shift>}c{/Shift}')
    expect(onAction).toHaveBeenCalledWith('prevScene')
  })

  it('does NOT dispatch when disabled', async () => {
    const onAction = vi.fn()
    render(<WaveformHotkeys enabled={false} onAction={onAction} />)

    await userEvent.keyboard('s')
    await userEvent.keyboard('d')
    await userEvent.keyboard(' ')

    expect(onAction).not.toHaveBeenCalled()
  })

  it('does NOT hijack typing inside an input element', async () => {
    const onAction = vi.fn()
    const { container } = render(
      <>
        <input data-testid="search" defaultValue="" />
        <WaveformHotkeys enabled={true} onAction={onAction} />
      </>,
    )
    const input = container.querySelector('input')!
    input.focus()

    await userEvent.type(input, 'sd')

    expect(onAction).not.toHaveBeenCalled()
    expect(input.value).toBe('sd')
  })

  it('does NOT hijack typing inside a textarea', async () => {
    const onAction = vi.fn()
    const { container } = render(
      <>
        <textarea data-testid="notes" defaultValue="" />
        <WaveformHotkeys enabled={true} onAction={onAction} />
      </>,
    )
    const textarea = container.querySelector('textarea')!
    textarea.focus()

    await userEvent.type(textarea, 'sg')

    expect(onAction).not.toHaveBeenCalled()
    expect(textarea.value).toBe('sg')
  })
})
