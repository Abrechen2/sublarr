import { useState, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useTemplateVariables, useEventCatalog } from '@/hooks/useApi'
import { Variable, ChevronDown, ToggleLeft, ToggleRight } from 'lucide-react'
import type { NotificationTemplate, TemplateVariable } from '@/lib/types'

interface TemplateEditorProps {
  template: Partial<NotificationTemplate>
  onChange: (update: Partial<NotificationTemplate>) => void
}

const JINJA_PATTERN = /\{\{.*?\}\}|\{%.*?%\}/g

function highlightJinja(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  const regex = new RegExp(JINJA_PATTERN.source, 'g')
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={lastIndex}>{text.slice(lastIndex, match.index)}</span>)
    }
    parts.push(
      <span key={match.index} style={{ color: 'var(--accent)', fontWeight: 500 }}>
        {match[0]}
      </span>
    )
    lastIndex = regex.lastIndex
  }
  if (lastIndex < text.length) {
    parts.push(<span key={lastIndex}>{text.slice(lastIndex)}</span>)
  }
  return parts
}

export function TemplateEditor({ template, onChange }: TemplateEditorProps) {
  const { t } = useTranslation('settings')
  const { data: catalogData } = useEventCatalog()
  const { data: variablesData } = useTemplateVariables(template.event_type ?? undefined)
  const [showVars, setShowVars] = useState(false)
  const titleRef = useRef<HTMLTextAreaElement>(null)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const [activeField, setActiveField] = useState<'title' | 'body'>('body')

  const eventTypes = catalogData?.events
    ? (catalogData.events as { name: string; label: string }[])
    : []
  const variables: TemplateVariable[] = variablesData?.variables ?? []

  const insertVariable = useCallback((varName: string) => {
    const ref = activeField === 'title' ? titleRef.current : bodyRef.current
    if (!ref) return
    const start = ref.selectionStart ?? 0
    const end = ref.selectionEnd ?? 0
    const fieldKey = activeField === 'title' ? 'title_template' : 'body_template'
    const current = (activeField === 'title' ? template.title_template : template.body_template) ?? ''
    const insertion = `{{ ${varName} }}`
    const newValue = current.slice(0, start) + insertion + current.slice(end)
    onChange({ [fieldKey]: newValue })

    // Restore cursor position after React re-render
    requestAnimationFrame(() => {
      if (ref) {
        ref.focus()
        const newPos = start + insertion.length
        ref.setSelectionRange(newPos, newPos)
      }
    })
  }, [activeField, template.title_template, template.body_template, onChange])

  return (
    <div className="space-y-3">
      {/* Name */}
      <div className="space-y-1">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {t('notifications.templates.name', 'Template Name')}
        </label>
        <input
          type="text"
          value={template.name ?? ''}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="e.g. Download Complete"
          className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
      </div>

      {/* Event Type & Service Name */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            {t('notifications.templates.eventType', 'Event Type')}
          </label>
          <div className="relative">
            <select
              value={template.event_type ?? ''}
              onChange={(e) => onChange({ event_type: e.target.value || null })}
              className="w-full px-3 py-2 rounded-md text-sm focus:outline-none appearance-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="">All Events</option>
              {eventTypes.map((evt) => (
                <option key={evt.name} value={evt.name}>{evt.label || evt.name}</option>
              ))}
            </select>
            <ChevronDown
              size={14}
              className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: 'var(--text-muted)' }}
            />
          </div>
        </div>
        <div className="space-y-1">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            {t('notifications.templates.serviceName', 'Service Name')}
          </label>
          <input
            type="text"
            value={template.service_name ?? ''}
            onChange={(e) => onChange({ service_name: e.target.value || null })}
            placeholder="Any service"
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
      </div>

      {/* Title Template */}
      <div className="space-y-1">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {t('notifications.templates.titleTemplate', 'Title Template')}
        </label>
        <div className="relative">
          <textarea
            ref={titleRef}
            value={template.title_template ?? ''}
            onChange={(e) => onChange({ title_template: e.target.value })}
            onFocus={() => setActiveField('title')}
            placeholder="{{ event_type }}: {{ title }}"
            rows={2}
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none resize-y"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
            }}
          />
          {template.title_template && (
            <div
              className="px-3 py-1 text-xs pointer-events-none"
              style={{ color: 'var(--text-muted)' }}
            >
              {highlightJinja(template.title_template)}
            </div>
          )}
        </div>
      </div>

      {/* Body Template */}
      <div className="space-y-1">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {t('notifications.templates.bodyTemplate', 'Body Template')}
        </label>
        <textarea
          ref={bodyRef}
          value={template.body_template ?? ''}
          onChange={(e) => onChange({ body_template: e.target.value })}
          onFocus={() => setActiveField('body')}
          placeholder="Subtitle {{ action }} for {{ title }} S{{ season }}E{{ episode }}"
          rows={5}
          className="w-full px-3 py-2 rounded-md text-sm focus:outline-none resize-y"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
          }}
        />
      </div>

      {/* Variables Panel */}
      <div>
        <button
          onClick={() => setShowVars((v) => !v)}
          className="flex items-center gap-1.5 text-xs font-medium"
          style={{ color: 'var(--accent)' }}
        >
          <Variable size={14} />
          {t('notifications.templates.variables', 'Available Variables')}
          <ChevronDown
            size={12}
            style={{ transform: showVars ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
          />
        </button>
        {showVars && variables.length > 0 && (
          <div
            className="mt-2 rounded-md p-3 grid grid-cols-1 sm:grid-cols-2 gap-1.5"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            {variables.map((v) => (
              <button
                key={v.name}
                onClick={() => insertVariable(v.name)}
                className="flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left transition-all duration-150"
                style={{ color: 'var(--text-secondary)' }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                title={v.description}
              >
                <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                  {'{{ '}{v.name}{' }}'}
                </code>
                <span className="truncate" style={{ color: 'var(--text-muted)' }}>
                  {v.sample_value}
                </span>
              </button>
            ))}
          </div>
        )}
        {showVars && variables.length === 0 && (
          <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            Select an event type to see available variables.
          </p>
        )}
      </div>

      {/* Enabled Toggle */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChange({ enabled: !template.enabled })}
          className="flex items-center gap-1.5"
        >
          {template.enabled !== false ? (
            <ToggleRight size={20} style={{ color: 'var(--accent)' }} />
          ) : (
            <ToggleLeft size={20} style={{ color: 'var(--text-muted)' }} />
          )}
        </button>
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {template.enabled !== false
            ? t('actions.enabled', 'Enabled')
            : t('actions.disabled', 'Disabled')}
        </span>
      </div>
    </div>
  )
}
