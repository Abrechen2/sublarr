/**
 * Widget chrome wrapper for dashboard grid items.
 *
 * Provides a consistent card with:
 * - Drag handle header (class "widget-drag-handle" for RGL config)
 * - Icon + translated title
 * - Optional remove (X) button
 * - Content area with optional padding
 */
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { WidgetDefinition } from './widgetRegistry'

interface WidgetWrapperProps {
  definition: WidgetDefinition
  children: React.ReactNode
  isEditMode?: boolean
  onRemove?: () => void
  noPadding?: boolean
}

export function WidgetWrapper({
  definition,
  children,
  isEditMode,
  onRemove,
  noPadding,
}: WidgetWrapperProps) {
  const { t } = useTranslation('dashboard')
  const Icon = definition.icon

  return (
    <div
      className="h-full flex flex-col rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}
    >
      {/* Drag Handle Header */}
      <div
        className="widget-drag-handle flex items-center justify-between px-3 py-2 cursor-grab active:cursor-grabbing select-none shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={14} style={{ color: 'var(--accent)' }} className="shrink-0" />
          <span
            className="text-xs font-semibold uppercase tracking-wider truncate"
            style={{ color: 'var(--text-muted)' }}
          >
            {t(definition.titleKey)}
          </span>
        </div>
        {isEditMode && onRemove && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onRemove()
            }}
            className="p-0.5 rounded hover:opacity-80 transition-opacity shrink-0"
            style={{ color: 'var(--text-muted)' }}
            title="Remove widget"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {/* Content Area */}
      <div className={`flex-1 overflow-auto${noPadding ? '' : ' p-4'}`}>
        {children}
      </div>
    </div>
  )
}
