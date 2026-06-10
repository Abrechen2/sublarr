/**
 * Shared primitives for the AutomationSettings section components.
 * Extracted from AutomationSettings.tsx during the file-size split.
 */
import { settingsInputStyle } from '@/styles/settingsShared'

export const inputStyle: React.CSSProperties = {
  ...settingsInputStyle,
  width: '220px',
  outline: 'none',
}

export const SCAN_ENGINES = ['auto', 'ffprobe', 'mediainfo'] as const

// ─── SectionSkeleton ─────────────────────────────────────────────────────────

export function SectionSkeleton() {
  return (
    <div data-testid="section-skeleton" className="animate-pulse space-y-3 py-2">
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          className="h-8 rounded"
          style={{ backgroundColor: 'var(--bg-surface-hover)', width: i === 0 ? '70%' : '100%' }}
        />
      ))}
    </div>
  )
}
