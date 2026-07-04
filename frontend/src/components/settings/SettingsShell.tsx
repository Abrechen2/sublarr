import type { ReactNode } from 'react'
import { SettingsNav } from './SettingsNav'

interface SettingsShellProps {
  readonly children: ReactNode
}

/**
 * Two-column layout for all /settings/* routes:
 * left = persistent navigation sidebar, right = page content.
 */
export function SettingsShell({ children }: SettingsShellProps) {
  return (
    <div
      data-testid="settings-shell"
      className="flex flex-col md:flex-row md:items-start gap-4 md:gap-6 w-full"
    >
      {/* Sidebar — full-width scrollable block on phones, sticky column from md up */}
      <div className="w-full max-h-64 overflow-y-auto md:w-auto md:max-h-screen md:sticky md:top-0">
        <SettingsNav />
      </div>

      {/* Divider (two-column layout only) */}
      <div
        className="hidden md:block"
        style={{
          width: 1,
          minHeight: '100%',
          background: 'var(--border)',
          flexShrink: 0,
          alignSelf: 'stretch',
        }}
      />

      {/* Page content */}
      <div className="flex-1 min-w-0 pb-10">
        {children}
      </div>
    </div>
  )
}
