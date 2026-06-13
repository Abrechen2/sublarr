import { useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * ApiKeyField — masked credential input with Test-Connection affordance.
 *
 * Codex blueprint #8: "API-Keys: maskiert speichern, `Test connection`
 * direkt daneben, letzte erfolgreiche Validierung und erkannte Scopes
 * anzeigen." This primitive encapsulates that pattern so every provider
 * editor and every connection editor uses the same contract.
 */

export interface ApiKeyTestResult {
  readonly ok: boolean
  /** Short human message, e.g. "Authenticated as abrechen2" or "403 — invalid key". */
  readonly detail?: string
  /** Scopes/permissions detected by the provider when the test succeeded. */
  readonly scopes?: readonly string[]
}

export interface ApiKeyFieldProps {
  readonly label: string
  readonly value: string
  readonly onChange: (next: string) => void
  /** Async test handler. If omitted, the Test button is hidden. */
  readonly onTest?: () => Promise<ApiKeyTestResult>
  readonly description?: ReactNode
  readonly placeholder?: string
  /** Human-readable freshness hint (e.g. "2 min ago") — rendered next to the status pill. */
  readonly lastValidatedLabel?: string | null
  readonly disabled?: boolean
}

export function ApiKeyField({
  label,
  value,
  onChange,
  onTest,
  description,
  placeholder,
  lastValidatedLabel,
  disabled = false,
}: ApiKeyFieldProps) {
  const { t } = useTranslation('settings')
  const [reveal, setReveal] = useState(false)
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<ApiKeyTestResult | null>(null)

  const runTest = useCallback(async () => {
    if (!onTest) return
    setTesting(true)
    try {
      const r = await onTest()
      setResult(r)
    } catch (err) {
      setResult({
        ok: false,
        detail: err instanceof Error ? err.message : t('api_key_field.test_failed'),
      })
    } finally {
      setTesting(false)
    }
  }, [onTest, t])

  // Prefer live test result; fall back to backend freshness hint.
  const statusPill: { cls: string; text: string } | null = result
    ? result.ok
      ? {
          cls: 'bg-[rgba(63,185,80,0.12)] text-[var(--success)]',
          text: `● ${result.detail ?? t('api_key_field.ok')}`,
        }
      : {
          cls: 'bg-[rgba(240,92,92,0.12)] text-[var(--error)]',
          text: `✕ ${result.detail ?? t('api_key_field.failed')}`,
        }
    : lastValidatedLabel
      ? {
          cls: 'bg-[rgba(63,185,80,0.12)] text-[var(--success)]',
          text: `● ${t('api_key_field.last_validated', { time: lastValidatedLabel })}`,
        }
      : null

  return (
    <div data-testid="api-key-field" className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-[12px] font-medium">{label}</span>
        {!disabled && value && (
          <button
            type="button"
            onClick={() => setReveal((v) => !v)}
            className="text-[10px] text-muted hover:text-primary"
          >
            {reveal ? t('api_key_field.hide') : t('api_key_field.reveal')}
          </button>
        )}
      </div>
      <input
        data-testid="api-key-input"
        type={reveal ? 'text' : 'password'}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="bg-[var(--bg-primary)] border border-[var(--border)] rounded px-2.5 py-2 text-[13px] font-mono tracking-wider text-primary focus:outline-none focus:border-[var(--accent)] disabled:opacity-60"
      />
      {description && <div className="text-[11px] text-muted">{description}</div>}

      {(onTest || statusPill || result?.scopes?.length) && (
        <div className="flex items-center gap-2 flex-wrap">
          {onTest && (
            <button
              type="button"
              onClick={runTest}
              disabled={testing || disabled || !value}
              data-testid="api-key-test-btn"
              className="text-[11px] font-semibold px-3 py-1.5 rounded bg-[var(--accent)] text-[#0a0f14] hover:bg-[var(--accent-dim)] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {testing ? t('api_key_field.testing') : t('api_key_field.test_connection')}
            </button>
          )}
          {statusPill && (
            <span
              data-testid="api-key-status"
              className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${statusPill.cls}`}
            >
              {statusPill.text}
            </span>
          )}
          {result?.scopes?.length ? (
            <span
              data-testid="api-key-scopes"
              className="text-[10px] text-muted"
            >
              {t('api_key_field.scopes', { scopes: result.scopes.join(', ') })}
            </span>
          ) : null}
        </div>
      )}
    </div>
  )
}
