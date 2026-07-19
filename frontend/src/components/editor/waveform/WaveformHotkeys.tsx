/**
 * WaveformHotkeys — registers the Aegisub-style keymap (Plan B8 Task 5).
 *
 * Renders nothing; the only side effect is registering global keybindings
 * via react-hotkeys-hook. We use one `useHotkeys` per shortcut so the
 * order is statically determined (Rules of Hooks-safe), and so that each
 * binding can carry its own preventDefault/scope flags later if needed.
 *
 * `enableOnFormTags: false` (the library default) makes typing in inputs
 * not hijack the editor's keymap — the user can still type 'd' inside
 * a Find & Replace box without setting a cue end.
 */

import { useHotkeys } from 'react-hotkeys-hook'

import type { WaveformAction } from './keymap'

export interface WaveformHotkeysProps {
  /** When false, no shortcut fires (e.g. the modal is closed). */
  enabled: boolean
  /** Receives every triggered action by id. */
  onAction: (action: WaveformAction) => void
}

export function WaveformHotkeys({ enabled, onAction }: WaveformHotkeysProps) {
  const opts = { enabled, preventDefault: true } as const

  useHotkeys('space', () => onAction('playPause'), opts)
  useHotkeys('s', () => onAction('setStart'), opts)
  useHotkeys('d', () => onAction('setEnd'), opts)
  useHotkeys('f', () => onAction('splitAtCursor'), opts)
  useHotkeys('g', () => onAction('mergeWithNext'), opts)
  useHotkeys('left', () => onAction('seekBack100ms'), opts)
  useHotkeys('right', () => onAction('seekFwd100ms'), opts)
  useHotkeys('shift+left', () => onAction('seekBack1s'), opts)
  useHotkeys('shift+right', () => onAction('seekFwd1s'), opts)
  useHotkeys('up', () => onAction('prevCue'), opts)
  useHotkeys('down', () => onAction('nextCue'), opts)
  useHotkeys('k', () => onAction('nextKeyframe'), opts)
  useHotkeys('shift+k', () => onAction('prevKeyframe'), opts)
  useHotkeys('n', () => onAction('nextDefect'), opts)
  useHotkeys('shift+n', () => onAction('prevDefect'), opts)
  useHotkeys('c', () => onAction('nextScene'), opts)
  useHotkeys('shift+c', () => onAction('prevScene'), opts)
  useHotkeys('+', () => onAction('zoomIn'), opts)
  useHotkeys('-', () => onAction('zoomOut'), opts)
  useHotkeys('shift+/', () => onAction('showHelp'), opts)

  return null
}
