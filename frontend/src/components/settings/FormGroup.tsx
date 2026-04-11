import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface FormGroupProps {
  readonly label: string
  readonly hint?: string
  readonly htmlFor?: string
  readonly fieldKey?: string
  readonly children: React.ReactNode
  readonly className?: string
  readonly 'data-testid'?: string
  readonly advanced?: boolean
}

// Inline styles for each pulse phase — no CSS animation needed
const HL_ON: React.CSSProperties = {
  backgroundColor: 'var(--accent-bg)',
  outline: '2px solid var(--accent)',
  borderRadius: '6px',
  transition: 'background-color 0.35s ease, outline-color 0.35s ease',
}
const HL_DIM: React.CSSProperties = {
  backgroundColor: 'var(--accent-bg)',
  outline: '2px solid var(--accent-dim)',
  borderRadius: '6px',
  transition: 'background-color 0.35s ease, outline-color 0.35s ease',
}
const HL_OFF: React.CSSProperties = {
  backgroundColor: 'transparent',
  outline: '2px solid transparent',
  borderRadius: '6px',
  transition: 'background-color 0.5s ease, outline-color 0.5s ease',
}
const HL_NONE: React.CSSProperties = {}

export function FormGroup({
  label,
  hint,
  htmlFor,
  fieldKey,
  children,
  className,
  'data-testid': testId,
  advanced = false,
}: FormGroupProps) {
  const { t } = useTranslation('settings')
  const [tooltipVisible, setTooltipVisible] = useState(false)
  const [hlStyle, setHlStyle] = useState<React.CSSProperties>(HL_NONE)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  const clearTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout)
    timersRef.current = []
  }, [])

  const checkHighlight = useCallback(() => {
    const target = sessionStorage.getItem('highlight-setting')
    if (!target) return
    const normalizedHtmlFor = htmlFor?.replace(/-/g, '_')
    if (fieldKey !== target && normalizedHtmlFor !== target) return

    sessionStorage.removeItem('highlight-setting')
    wrapperRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })

    clearTimers()

    // Pulse sequence: ON → DIM → ON → DIM → ON → fade OFF → reset
    setHlStyle(HL_ON)
    const schedule = (fn: () => void, ms: number) => {
      const id = setTimeout(fn, ms)
      timersRef.current.push(id)
    }
    schedule(() => setHlStyle(HL_DIM), 1000)
    schedule(() => setHlStyle(HL_ON),  2000)
    schedule(() => setHlStyle(HL_DIM), 3000)
    schedule(() => setHlStyle(HL_ON),  4000)
    schedule(() => setHlStyle(HL_OFF), 4500)
    schedule(() => setHlStyle(HL_NONE), 5100)
  }, [htmlFor, fieldKey, clearTimers])

  // Cross-page navigation: run on mount
  useEffect(() => { checkHighlight() }, [checkHighlight])

  // Same-page navigation: custom event from search modal
  useEffect(() => {
    window.addEventListener('settings-highlight-request', checkHighlight)
    return () => window.removeEventListener('settings-highlight-request', checkHighlight)
  }, [checkHighlight])

  // Cleanup timers on unmount
  useEffect(() => clearTimers, [clearTimers])

  return (
    <div
      ref={wrapperRef}
      data-testid={testId ?? 'form-group'}
      className={cn(
        'flex flex-col md:flex-row md:items-start md:justify-between gap-2',
        'last:border-b-0 last:pb-0 first:pt-0',
        className,
      )}
      style={{
        padding: '12px 0',
        borderBottom: '1px solid var(--border)',
        ...hlStyle,
      }}
    >
      {/* Label group — left side */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0" style={{ maxWidth: '320px' }}>
        <div className="flex items-center gap-1.5 flex-wrap">
          {htmlFor ? (
            <label
              htmlFor={htmlFor}
              data-testid="form-group-label"
              className="text-[13px] font-medium text-[var(--text-primary)] cursor-pointer"
            >
              {label}
            </label>
          ) : (
            <span
              data-testid="form-group-label"
              className="text-[13px] font-medium text-[var(--text-primary)]"
            >
              {label}
            </span>
          )}

          {advanced && (
            <>
              <span
                data-testid="form-group-advanced-badge"
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  color: 'var(--warning, #f59e0b)',
                  background: 'rgba(245,158,11,0.12)',
                  border: '1px solid rgba(245,158,11,0.3)',
                  borderRadius: '3px',
                  padding: '1px 6px',
                  lineHeight: '1.4',
                }}
              >
                {t('advanced_badge')}
              </span>

              {hint && (
                <div
                  style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
                  onMouseEnter={() => setTooltipVisible(true)}
                  onMouseLeave={() => setTooltipVisible(false)}
                >
                  <button
                    type="button"
                    data-testid="form-group-info-icon"
                    aria-label="Show hint"
                    style={{
                      width: '15px',
                      height: '15px',
                      borderRadius: '50%',
                      background: 'var(--accent-bg)',
                      border: '1px solid var(--accent-dim)',
                      color: 'var(--accent)',
                      fontSize: '9px',
                      fontWeight: 700,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'default',
                      flexShrink: 0,
                    }}
                  >
                    i
                  </button>
                  {tooltipVisible && (
                    <div
                      data-testid="form-group-tooltip"
                      role="tooltip"
                      style={{
                        position: 'absolute',
                        left: '20px',
                        top: '-4px',
                        zIndex: 100,
                        background: 'var(--bg-elevated)',
                        border: '1px solid var(--accent-dim)',
                        borderRadius: '6px',
                        padding: '8px 10px',
                        fontSize: '11px',
                        color: 'var(--text-secondary)',
                        width: '220px',
                        lineHeight: '1.5',
                        whiteSpace: 'normal',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                        pointerEvents: 'none',
                      }}
                    >
                      {hint}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Inline hint — only when not advanced */}
        {!advanced && hint && (
          <span
            data-testid="form-group-hint"
            className="text-[11px] leading-relaxed text-[var(--text-muted)]"
          >
            {hint}
          </span>
        )}
      </div>

      {/* Control group — right side */}
      <div
        data-testid="form-group-control"
        className="flex items-center gap-2"
        style={{ minWidth: '260px', justifyContent: 'flex-end' }}
      >
        {children}
      </div>
    </div>
  )
}
