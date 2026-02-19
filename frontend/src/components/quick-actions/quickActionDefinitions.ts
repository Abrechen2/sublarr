import type { LucideIcon } from 'lucide-react'
import { RefreshCw, Search, CheckSquare, ShieldCheck } from 'lucide-react'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface QuickActionTemplate {
  readonly id: string
  readonly labelKey: string        // i18n key in common namespace
  readonly icon: LucideIcon
  readonly shortcut: string        // Display string like "Shift+S"
  readonly hotkeyCombo: string     // react-hotkeys-hook format like "shift+s"
}

export interface GlobalShortcutInfo {
  readonly id: string
  readonly labelKey: string
  readonly shortcut: string
  readonly category: string
}

// ─── Per-Route Action Templates ──────────────────────────────────────────────

const DASHBOARD_ACTIONS: readonly QuickActionTemplate[] = [
  {
    id: 'scan_library',
    labelKey: 'common:quick_actions.scan_library',
    icon: RefreshCw,
    shortcut: 'Shift+S',
    hotkeyCombo: 'shift+s',
  },
  {
    id: 'search_wanted',
    labelKey: 'common:quick_actions.search_wanted',
    icon: Search,
    shortcut: 'Shift+W',
    hotkeyCombo: 'shift+w',
  },
] as const

const WANTED_ACTIONS: readonly QuickActionTemplate[] = [
  {
    id: 'refresh_scan',
    labelKey: 'common:quick_actions.refresh_scan',
    icon: RefreshCw,
    shortcut: 'Shift+R',
    hotkeyCombo: 'shift+r',
  },
  {
    id: 'search_all',
    labelKey: 'common:quick_actions.search_all',
    icon: Search,
    shortcut: 'Shift+S',
    hotkeyCombo: 'shift+s',
  },
  {
    id: 'select_all',
    labelKey: 'common:quick_actions.select_all',
    icon: CheckSquare,
    shortcut: 'Shift+A',
    hotkeyCombo: 'shift+a',
  },
] as const

const LIBRARY_ACTIONS: readonly QuickActionTemplate[] = [
  {
    id: 'refresh_scan',
    labelKey: 'common:quick_actions.refresh_scan',
    icon: RefreshCw,
    shortcut: 'Shift+R',
    hotkeyCombo: 'shift+r',
  },
] as const

const SERIES_DETAIL_ACTIONS: readonly QuickActionTemplate[] = [
  {
    id: 'health_check',
    labelKey: 'common:quick_actions.health_check',
    icon: ShieldCheck,
    shortcut: 'Shift+H',
    hotkeyCombo: 'shift+h',
  },
] as const

const HISTORY_ACTIONS: readonly QuickActionTemplate[] = [
  {
    id: 'select_all',
    labelKey: 'common:quick_actions.select_all',
    icon: CheckSquare,
    shortcut: 'Shift+A',
    hotkeyCombo: 'shift+a',
  },
] as const

// ─── Route Matching ──────────────────────────────────────────────────────────

export function getActionTemplatesForRoute(pathname: string): readonly QuickActionTemplate[] {
  if (pathname === '/') return DASHBOARD_ACTIONS
  if (pathname === '/wanted') return WANTED_ACTIONS
  if (pathname === '/library') return LIBRARY_ACTIONS
  if (pathname.startsWith('/library/series/')) return SERIES_DETAIL_ACTIONS
  if (pathname === '/history') return HISTORY_ACTIONS
  return []
}

// ─── Global Shortcuts (for documentation in modal) ──────────────────────────

export const GLOBAL_SHORTCUTS: readonly GlobalShortcutInfo[] = [
  // Navigation
  { id: 'nav_dashboard', labelKey: 'common:shortcuts.go_dashboard', shortcut: 'g then d', category: 'navigation' },
  { id: 'nav_library', labelKey: 'common:shortcuts.go_library', shortcut: 'g then l', category: 'navigation' },
  { id: 'nav_wanted', labelKey: 'common:shortcuts.go_wanted', shortcut: 'g then w', category: 'navigation' },
  { id: 'nav_settings', labelKey: 'common:shortcuts.go_settings', shortcut: 'g then s', category: 'navigation' },
  { id: 'nav_activity', labelKey: 'common:shortcuts.go_activity', shortcut: 'g then a', category: 'navigation' },
  { id: 'nav_history', labelKey: 'common:shortcuts.go_history', shortcut: 'g then h', category: 'navigation' },
  // Global
  { id: 'global_search', labelKey: 'common:shortcuts.search', shortcut: 'Ctrl+K', category: 'global' },
  { id: 'global_help', labelKey: 'common:shortcuts.help', shortcut: 'Shift+/', category: 'global' },
] as const
