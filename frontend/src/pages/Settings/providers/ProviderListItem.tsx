import { GripVertical } from 'lucide-react'
import type { ProviderInfo } from '@/lib/types'
import { getStatusColor } from './providerUtils'

interface ProviderListItemProps {
  provider: ProviderInfo
  priority: number
  isActive: boolean
  isDragging: boolean
  isDragOver: boolean
}

/**
 * Compact list-row used inside CollectionLayout's master list. Replaces the
 * tile-grid presentation for the Providers Settings page (Codex Template A
 * reference). The clickable wrapper is provided by CollectionLayout itself —
 * this component renders the inner row only.
 */
export function ProviderListItem({
  provider, priority, isActive, isDragging, isDragOver,
}: ProviderListItemProps) {
  const statusColor = getStatusColor(provider)
  const rankLabel = provider.enabled ? `#${priority}` : 'off'

  return (
    <div
      className="flex items-center gap-2 w-full"
      style={{
        opacity: isDragging ? 0.5 : provider.enabled ? 1 : 0.6,
        outline: isDragOver && !isDragging ? '2px solid var(--accent)' : 'none',
        outlineOffset: '2px',
      }}
    >
      <GripVertical
        size={12}
        style={{ color: 'var(--text-muted)', flexShrink: 0 }}
        aria-hidden="true"
      />
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ backgroundColor: statusColor }}
        aria-hidden="true"
      />
      <span
        className="text-[12px] font-medium capitalize truncate flex-1"
        style={{ color: isActive ? 'var(--accent)' : 'var(--text-primary)' }}
      >
        {provider.name.replace(/_/g, ' ')}
      </span>
      <span className="text-[10px] shrink-0" style={{ color: 'var(--text-muted)' }}>
        {rankLabel}
      </span>
    </div>
  )
}
