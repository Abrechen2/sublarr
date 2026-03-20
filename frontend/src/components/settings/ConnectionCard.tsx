/**
 * ConnectionCard — displays a service connection (Sonarr, Radarr, etc.)
 * with status badge, URL display, test button, and inline edit form.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TestTube, Edit2, ChevronDown, ChevronUp, Eye, EyeOff, Loader2, Check, X } from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ConnectionCardStatus = 'connected' | 'unconfigured' | 'error'

export interface ConnectionCardField {
  readonly key: string
  readonly label: string
  readonly type: 'text' | 'password'
  readonly placeholder?: string
  readonly value: string
  readonly onChange: (value: string) => void
}

export interface ConnectionCardProps {
  /** Two-letter abbreviation shown in the colored box (e.g. "SN", "RD") */
  readonly abbr: string
  /** Accent color for the abbreviation box background */
  readonly color: string
  /** Full service name (e.g. "Sonarr", "Radarr") */
  readonly name: string
  readonly status: ConnectionCardStatus
  /** Optional URL to display when collapsed */
  readonly url?: string
  /** Optional item count to display (e.g. number of series/movies) */
  readonly itemCount?: number
  /** Inline-edit form fields */
  readonly fields: readonly ConnectionCardField[]
  /** Called when the Test button is clicked */
  readonly onTest: () => void
  /** Called when Save is clicked in expanded form */
  readonly onSave: () => void
  /** True while a test mutation is in-flight */
  readonly isTesting?: boolean
  /** True while a save mutation is in-flight */
  readonly isSaving?: boolean
  /** Optional message from last test result */
  readonly testMessage?: string | null
  /** data-testid for the root element */
  readonly 'data-testid'?: string
}

// ─── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ConnectionCardStatus }) {
  const { t } = useTranslation('common')

  const config: Record<ConnectionCardStatus, { label: string; bg: string; color: string }> = {
    connected: {
      label: t('status.healthy'),
      bg: 'rgba(16, 185, 129, 0.12)',
      color: 'var(--success)',
    },
    unconfigured: {
      label: t('status.not_configured'),
      bg: 'rgba(124, 130, 147, 0.10)',
      color: 'var(--text-muted)',
    },
    error: {
      label: t('status.failed'),
      bg: 'rgba(239, 68, 68, 0.12)',
      color: 'var(--error)',
    },
  }

  const { label, bg, color } = config[status]

  return (
    <span
      data-testid="connection-card-status-badge"
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold"
      style={{ backgroundColor: bg, color }}
    >
      {label}
    </span>
  )
}

// ─── ConnectionCard ───────────────────────────────────────────────────────────

export function ConnectionCard({
  abbr,
  color,
  name,
  status,
  url,
  itemCount,
  fields,
  onTest,
  onSave,
  isTesting = false,
  isSaving = false,
  testMessage,
  'data-testid': testId = 'connection-card',
}: ConnectionCardProps) {
  const { t } = useTranslation('common')
  const [expanded, setExpanded] = useState(false)
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})

  const togglePassword = (key: string) => {
    setShowPasswords((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const handleSave = () => {
    onSave()
    setExpanded(false)
  }

  const handleCancel = () => {
    setExpanded(false)
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
  } as const

  return (
    <div
      data-testid={testId}
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}
    >
      {/* ── Collapsed header ── */}
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Service abbreviation box */}
        <div
          data-testid="connection-card-abbr"
          className="flex items-center justify-center w-9 h-9 rounded-md flex-shrink-0 text-white text-xs font-bold"
          style={{ backgroundColor: color }}
        >
          {abbr}
        </div>

        {/* Name + status + URL */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              data-testid="connection-card-name"
              className="text-sm font-semibold"
              style={{ color: 'var(--text-primary)' }}
            >
              {name}
            </span>
            <StatusBadge status={status} />
          </div>
          {url && (
            <span
              data-testid="connection-card-url"
              className="text-xs truncate block"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {url}
            </span>
          )}
          {itemCount !== undefined && (
            <span
              data-testid="connection-card-item-count"
              className="text-xs"
              style={{ color: 'var(--text-muted)' }}
            >
              {itemCount} items
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            data-testid="connection-card-test-btn"
            onClick={onTest}
            disabled={isTesting}
            title={t('actions.test')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
              opacity: isTesting ? 0.6 : 1,
            }}
            onMouseEnter={(e) => {
              if (!isTesting) {
                e.currentTarget.style.borderColor = 'var(--accent-dim)'
                e.currentTarget.style.color = 'var(--accent)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }}
          >
            {isTesting ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <TestTube size={12} />
            )}
            {t('actions.test')}
          </button>

          <button
            data-testid="connection-card-edit-btn"
            onClick={() => setExpanded((prev) => !prev)}
            title={t('actions.edit')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--accent-dim)'
              e.currentTarget.style.color = 'var(--accent)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }}
          >
            <Edit2 size={12} />
            {t('actions.edit')}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {/* Test result inline message */}
      {testMessage && (
        <div
          data-testid="connection-card-test-message"
          className="px-4 pb-2 text-xs"
          style={{
            color: status === 'connected' ? 'var(--success)' : 'var(--error)',
          }}
        >
          {testMessage}
        </div>
      )}

      {/* ── Expanded edit form ── */}
      {expanded && (
        <div
          data-testid="connection-card-form"
          className="px-4 pb-4 pt-3 space-y-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          {fields.map((field) => {
            const isPassword = field.type === 'password'
            const shown = showPasswords[field.key]
            return (
              <div key={field.key} className="space-y-1">
                <label
                  htmlFor={`connection-card-field-${field.key}`}
                  className="block text-xs font-medium"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {field.label}
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    id={`connection-card-field-${field.key}`}
                    data-testid={`connection-card-field-${field.key}`}
                    type={isPassword && !shown ? 'password' : 'text'}
                    value={field.value}
                    onChange={(e) => field.onChange(e.target.value)}
                    placeholder={field.placeholder}
                    className="flex-1 px-2.5 py-1.5 rounded text-xs focus:outline-none"
                    style={inputStyle}
                  />
                  {isPassword && (
                    <button
                      data-testid={`connection-card-toggle-${field.key}`}
                      type="button"
                      onClick={() => togglePassword(field.key)}
                      className="p-1.5 rounded"
                      style={{
                        border: '1px solid var(--border)',
                        color: 'var(--text-muted)',
                        backgroundColor: 'var(--bg-primary)',
                      }}
                      title={shown ? 'Hide' : 'Show'}
                    >
                      {shown ? <EyeOff size={12} /> : <Eye size={12} />}
                    </button>
                  )}
                </div>
              </div>
            )
          })}

          {/* Form actions */}
          <div className="flex items-center gap-2 pt-1">
            <button
              data-testid="connection-card-save-btn"
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)', opacity: isSaving ? 0.6 : 1 }}
            >
              {isSaving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              {t('actions.save')}
            </button>
            <button
              data-testid="connection-card-cancel-btn"
              onClick={handleCancel}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <X size={12} />
              {t('actions.cancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
