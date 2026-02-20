import { useHotkeys } from 'react-hotkeys-hook'
import { useNavigate } from 'react-router-dom'

interface UseKeyboardShortcutsOptions {
  readonly onToggleShortcutsModal: () => void
}

/**
 * Registers global keyboard shortcuts for navigation and help.
 * Must be called inside a BrowserRouter context (needs useNavigate).
 *
 * Navigation: g then d/l/w/s/a/h
 * Help: Shift+/ (the "?" key)
 *
 * NOTE: Ctrl+K (search) is handled separately in App.tsx to avoid double-fire
 * with the existing GlobalSearchModal handler.
 */
export function useKeyboardShortcuts({ onToggleShortcutsModal }: UseKeyboardShortcutsOptions): void {
  const navigate = useNavigate()

  // Navigation shortcuts: g then <key>
  useHotkeys('g then d', () => { void navigate('/') }, {
    preventDefault: true,
  })

  useHotkeys('g then l', () => { void navigate('/library') }, {
    preventDefault: true,
  })

  useHotkeys('g then w', () => { void navigate('/wanted') }, {
    preventDefault: true,
  })

  useHotkeys('g then s', () => { void navigate('/settings') }, {
    preventDefault: true,
  })

  useHotkeys('g then a', () => { void navigate('/activity') }, {
    preventDefault: true,
  })

  useHotkeys('g then h', () => { void navigate('/history') }, {
    preventDefault: true,
  })

  // Help shortcut: Shift+/ = "?" key
  useHotkeys('shift+/', () => {
    onToggleShortcutsModal()
  }, {
    preventDefault: true,
  })
}
