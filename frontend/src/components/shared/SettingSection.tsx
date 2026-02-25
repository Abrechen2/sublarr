import type { ReactNode } from 'react'

interface SettingSectionProps {
  title: string
  description?: string
  children: ReactNode
}

export function SettingSection({ title, description, children }: SettingSectionProps) {
  return (
    <div className="mt-6 first:mt-0">
      <div
        className="pb-2 mb-0"
        style={{ borderBottom: '1px solid var(--border)' }}
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
      <div className="space-y-4 pt-4">{children}</div>
    </div>
  )
}
