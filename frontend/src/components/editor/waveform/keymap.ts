/**
 * Waveform editor keymap (Plan B8 Task 5).
 *
 * Single source of truth for the Aegisub-style shortcut surface. Used by:
 *   - `WaveformHotkeys.tsx` to register the bindings via react-hotkeys-hook
 *   - `WaveformShortcutHelp.tsx` to render the `?` overlay
 *   - i18n: `editor.waveform.shortcut.<labelKey>` is the lookup key for the
 *     human-readable label, kept in `frontend/src/i18n/locales/{en,de}/editor.json`
 *
 * Pattern follows Aegisub Medusa defaults:
 *   - S/D : set start / end of the selected cue at current playback time
 *   - F/G : split / merge cues
 *   - arrows: nudge playhead; with shift, larger step
 *   - up/down: previous / next cue
 *   - +/-  : zoom in / out
 *   - ?   : help overlay
 */

export type WaveformAction =
  | 'playPause'
  | 'setStart'
  | 'setEnd'
  | 'splitAtCursor'
  | 'mergeWithNext'
  | 'seekBack100ms'
  | 'seekFwd100ms'
  | 'seekBack1s'
  | 'seekFwd1s'
  | 'prevCue'
  | 'nextCue'
  | 'prevKeyframe'
  | 'nextKeyframe'
  | 'prevDefect'
  | 'nextDefect'
  | 'zoomIn'
  | 'zoomOut'
  | 'showHelp'

export type WaveformShortcutGroup =
  | 'playback'
  | 'timing'
  | 'navigation'
  | 'markers'
  | 'zoom'
  | 'help'

export interface WaveformShortcut {
  /** react-hotkeys-hook key string. Modifiers separated by `+`. */
  keys: string
  /** Human-friendly key label shown in the help overlay (independent of the
   *  registration string so we can render `Space` instead of literal ` `). */
  display: string
  action: WaveformAction
  /** i18n suffix under `editor.waveform.shortcut.`. */
  labelKey: string
  group: WaveformShortcutGroup
}

export const WAVEFORM_SHORTCUTS: readonly WaveformShortcut[] = [
  { keys: 'space', display: 'Space', action: 'playPause', labelKey: 'playPause', group: 'playback' },
  { keys: 's', display: 'S', action: 'setStart', labelKey: 'setStart', group: 'timing' },
  { keys: 'd', display: 'D', action: 'setEnd', labelKey: 'setEnd', group: 'timing' },
  { keys: 'f', display: 'F', action: 'splitAtCursor', labelKey: 'splitAtCursor', group: 'timing' },
  { keys: 'g', display: 'G', action: 'mergeWithNext', labelKey: 'mergeWithNext', group: 'timing' },
  { keys: 'left', display: '←', action: 'seekBack100ms', labelKey: 'seekBack100ms', group: 'navigation' },
  { keys: 'right', display: '→', action: 'seekFwd100ms', labelKey: 'seekFwd100ms', group: 'navigation' },
  { keys: 'shift+left', display: 'Shift+←', action: 'seekBack1s', labelKey: 'seekBack1s', group: 'navigation' },
  { keys: 'shift+right', display: 'Shift+→', action: 'seekFwd1s', labelKey: 'seekFwd1s', group: 'navigation' },
  { keys: 'up', display: '↑', action: 'prevCue', labelKey: 'prevCue', group: 'navigation' },
  { keys: 'down', display: '↓', action: 'nextCue', labelKey: 'nextCue', group: 'navigation' },
  { keys: 'k', display: 'K', action: 'nextKeyframe', labelKey: 'nextKeyframe', group: 'markers' },
  { keys: 'shift+k', display: 'Shift+K', action: 'prevKeyframe', labelKey: 'prevKeyframe', group: 'markers' },
  { keys: 'n', display: 'N', action: 'nextDefect', labelKey: 'nextDefect', group: 'markers' },
  { keys: 'shift+n', display: 'Shift+N', action: 'prevDefect', labelKey: 'prevDefect', group: 'markers' },
  { keys: '+', display: '+', action: 'zoomIn', labelKey: 'zoomIn', group: 'zoom' },
  { keys: '-', display: '−', action: 'zoomOut', labelKey: 'zoomOut', group: 'zoom' },
  { keys: 'shift+/', display: '?', action: 'showHelp', labelKey: 'showHelp', group: 'help' },
] as const

/** Render order for the help overlay. */
export const WAVEFORM_SHORTCUT_GROUPS: readonly WaveformShortcutGroup[] = [
  'playback',
  'timing',
  'navigation',
  'markers',
  'zoom',
  'help',
]
