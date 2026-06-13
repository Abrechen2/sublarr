import { useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * ConnectionTest — a reusable test-connection button with a state machine.
 *
 * The same pattern repeats in Sonarr/Radarr connections, MediaServer
 * connectors, Ollama health checks, and every provider editor. Extracted
 * now (Codex recommendation) instead of duplicating across 6+ call sites.
 *
 * State machine:
 *   idle → testing → (ok | fail) → idle (on re-click)
 *
 * The caller supplies `onTest`. ConnectionTest owns the transient
 * testing/ok/fail states; it does NOT persist "last validated" — that's a
 * backend concern exposed separately (see ApiKeyField's
 * `lastValidatedLabel` prop).
 */

export type ConnectionTestState = 'idle' | 'testing' | 'ok' | 'fail'

export interface ConnectionTestResult {
  readonly ok: boolean
  /** Short human message shown in the status pill after the test. */
  readonly detail?: string
  /** Optional extra context (e.g. detected API version, scopes, server name). */
  readonly meta?: ReactNode
}

export interface ConnectionTestProps {
  /** Button label — typically a translated string like t('settings.common.test_connection'). */
  readonly label: string
  /** Async handler that performs the test. Exceptions are coerced to fail state. */
  readonly onTest: () => Promise<ConnectionTestResult>
  readonly disabled?: boolean
  readonly size?: 'sm' | 'md'
  /**
   * Optional: fires after the test resolves, regardless of outcome. Use this
   * to bubble the result up to a parent store (e.g. cache a lastValidated
   * timestamp, invalidate a react-query health query).
   */
  readonly onResult?: (result: ConnectionTestResult) => void
  /** Custom data-testid prefix. Defaults to 'connection-test'. */
  readonly testIdPrefix?: string
}

const sizeClasses: Record<NonNullable<ConnectionTestProps['size']>, string> = {
  sm: 'text-[10px] px-2 py-1',
  md: 'text-[11px] px-3 py-1.5',
}

export function ConnectionTest({
  label,
  onTest,
  disabled = false,
  size = 'md',
  onResult,
  testIdPrefix = 'connection-test',
}: ConnectionTestProps) {
  const { t } = useTranslation('settings')
  const [state, setState] = useState<ConnectionTestState>('idle')
  const [result, setResult] = useState<ConnectionTestResult | null>(null)

  const run = useCallback(async () => {
    if (disabled || state === 'testing') return
    setState('testing')
    setResult(null)
    try {
      const r = await onTest()
      setState(r.ok ? 'ok' : 'fail')
      setResult(r)
      onResult?.(r)
    } catch (err) {
      const failResult: ConnectionTestResult = {
        ok: false,
        detail: err instanceof Error ? err.message : t('connection_test.test_failed'),
      }
      setState('fail')
      setResult(failResult)
      onResult?.(failResult)
    }
  }, [disabled, state, onTest, onResult, t])

  const pillClass = (() => {
    switch (state) {
      case 'ok':
        return 'bg-[rgba(63,185,80,0.12)] text-[var(--success)]'
      case 'fail':
        return 'bg-[rgba(240,92,92,0.12)] text-[var(--error)]'
      case 'testing':
        return 'bg-[rgba(232,163,61,0.12)] text-[var(--warning)]'
      default:
        return ''
    }
  })()

  const pillPrefix = (() => {
    switch (state) {
      case 'ok':
        return '●'
      case 'fail':
        return '✕'
      case 'testing':
        return '●'
      default:
        return ''
    }
  })()

  const pillText = (() => {
    if (state === 'testing') return t('connection_test.testing')
    if (result?.detail) return result.detail
    if (state === 'ok') return t('connection_test.ok')
    if (state === 'fail') return t('connection_test.failed')
    return ''
  })()

  return (
    <div
      data-testid={testIdPrefix}
      data-state={state}
      className="flex items-center gap-2 flex-wrap"
    >
      <button
        type="button"
        onClick={run}
        disabled={disabled || state === 'testing'}
        data-testid={`${testIdPrefix}-btn`}
        className={`font-semibold rounded bg-[var(--accent)] text-[#0a0f14] hover:bg-[var(--accent-dim)] disabled:opacity-60 disabled:cursor-not-allowed ${sizeClasses[size]}`}
      >
        {state === 'testing' ? t('connection_test.testing') : label}
      </button>

      {state !== 'idle' && (
        <span
          data-testid={`${testIdPrefix}-pill`}
          className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${pillClass}`}
        >
          {pillPrefix} {pillText}
        </span>
      )}

      {state === 'ok' && result?.meta && (
        <span data-testid={`${testIdPrefix}-meta`} className="text-[10px] text-muted">
          {result.meta}
        </span>
      )}
    </div>
  )
}
