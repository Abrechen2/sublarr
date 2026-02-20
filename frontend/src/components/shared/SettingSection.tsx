import type { ReactNode } from 'react'

interface SettingSectionProps {
  title: string
  description?: string
  children: ReactNode
}

export function SettingSection({ title, description, children }: SettingSectionProps) {
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div
        className="px-5 py-3"
        style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
      >
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h3>
        {description && (
          <p className="mt-0.5 text-xs" style={{ color: 'var(--text-muted)' }}>
            {description}
          </p>
        )}
      </div>
      <div className="px-5 py-4 space-y-4">{children}</div>
    </div>
  )
}
