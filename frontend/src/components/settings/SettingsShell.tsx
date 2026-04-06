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
      className="flex gap-6 w-full"
      style={{ alignItems: 'flex-start' }}
    >
      {/* Sticky sidebar */}
      <div
        style={{
          position: 'sticky',
          top: 0,
          maxHeight: '100vh',
          overflowY: 'auto',
        }}
      >
        <SettingsNav />
      </div>

      {/* Divider */}
      <div
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
