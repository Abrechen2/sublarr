import { useState, useCallback } from 'react'
import {
  Loader2, RefreshCw, Wrench, XCircle, AlertTriangle, Info,
  CheckCircle2, X,
} from 'lucide-react'
import { useHealthCheck, useHealthFix } from '@/hooks/useApi'
import { HealthBadge } from './HealthBadge'
import { toast } from '@/components/shared/Toast'
import type { HealthIssue } from '@/lib/types'

interface HealthCheckPanelProps {
  filePath: string
  onClose?: () => void
  onFixed?: () => void
}

function severityIcon(severity: HealthIssue['severity']) {
  switch (severity) {
    case 'error':
      return <XCircle size={14} style={{ color: 'var(--error)' }} />
    case 'warning':
      return <AlertTriangle size={14} style={{ color: 'var(--warning)' }} />
    case 'info':
      return <Info size={14} style={{ color: 'var(--accent)' }} />
  }
}

function severityOrder(severity: HealthIssue['severity']): number {
  switch (severity) {
    case 'error': return 0
    case 'warning': return 1
    case 'info': return 2
  }
}

export function HealthCheckPanel({ filePath, onClose, onFixed }: HealthCheckPanelProps) {
  const { data, isLoading, refetch } = useHealthCheck(filePath)
  const healthFix = useHealthFix()
  const [showConfirm, setShowConfirm] = useState(false)

  const fileName = filePath.split('/').pop() || filePath.split('\\').pop() || filePath

  const issues = data?.issues ?? []
  const sortedIssues = [...issues].sort(
    (a, b) => severityOrder(a.severity) - severityOrder(b.severity)
  )
  const fixableIssues = issues.filter((i) => i.auto_fixable)
  const fixableChecks = [...new Set(fixableIssues.map((i) => i.check))]

  const handleFixSingle = useCallback(
    (checkName: string) => {
      healthFix.mutate(
        { filePath, fixes: [checkName] },
        {
          onSuccess: (result) => {
            toast(`Fixed. New score: ${result.new_score}`)
            void refetch()
            onFixed?.()
          },
          onError: () => toast('Fix failed', 'error'),
        }
      )
    },
    [filePath, healthFix, refetch, onFixed]
  )

  const handleFixAll = useCallback(() => {
    healthFix.mutate(
      { filePath, fixes: fixableChecks },
      {
        onSuccess: (result) => {
          toast(`Fixed ${result.fixes_applied.length} issues. New score: ${result.new_score}`)
          setShowConfirm(false)
          void refetch()
          onFixed?.()
        },
        onError: () => toast('Batch fix failed', 'error'),
      }
    )
  }, [filePath, fixableChecks, healthFix, refetch, onFixed])

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        maxHeight: '70vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="text-sm font-medium truncate"
            title={filePath}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
          >
            {fileName}
          </span>
          {data && <HealthBadge score={data.score} size="md" />}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => void refetch()}
            disabled={isLoading}
            className="p-1.5 rounded transition-colors"
            style={{ color: 'var(--text-muted)' }}
            title="Re-check"
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
              title="Close"
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-8" style={{ color: 'var(--text-secondary)' }}>
          <Loader2 size={16} className="animate-spin" />
          <span className="text-sm">Running health checks...</span>
        </div>
      )}

      {/* Content */}
      {data && !isLoading && (
        <div className="flex-1 overflow-y-auto">
          {/* Batch fix bar */}
          {fixableIssues.length > 0 && !showConfirm && (
            <div
              className="flex items-center justify-between px-4 py-2"
              style={{ backgroundColor: 'var(--bg-primary)', borderBottom: '1px solid var(--border)' }}
            >
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {fixableIssues.length} auto-fixable issue{fixableIssues.length !== 1 ? 's' : ''}
              </span>
              <button
                onClick={() => setShowConfirm(true)}
                className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                <Wrench size={11} />
                Fix All ({fixableChecks.length})
              </button>
            </div>
          )}

          {/* Confirm batch fix */}
          {showConfirm && (
            <div
              className="px-4 py-3 space-y-2"
              style={{ backgroundColor: 'var(--warning-bg)', borderBottom: '1px solid var(--border)' }}
            >
              <div className="text-xs font-semibold" style={{ color: 'var(--warning)' }}>
                Fixes to apply:
              </div>
              <ul className="text-xs space-y-0.5" style={{ color: 'var(--text-primary)' }}>
                {fixableIssues.map((issue, i) => (
                  <li key={i}>- {issue.fix || issue.message}</li>
                ))}
              </ul>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleFixAll}
                  disabled={healthFix.isPending}
                  className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {healthFix.isPending ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    <Wrench size={11} />
                  )}
                  Confirm
                </button>
                <button
                  onClick={() => setShowConfirm(false)}
                  className="px-3 py-1 rounded text-xs"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Issues list */}
          {sortedIssues.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8" style={{ color: 'var(--success)' }}>
              <CheckCircle2 size={28} />
              <span className="text-sm font-medium">No issues found. Score: 100</span>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {sortedIssues.map((issue, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 px-4 py-2.5"
                >
                  <div className="mt-0.5 flex-shrink-0">
                    {severityIcon(issue.severity)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs" style={{ color: 'var(--text-primary)' }}>
                      {issue.message}
                    </div>
                    {issue.line !== null && (
                      <span
                        className="inline-flex mt-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{
                          backgroundColor: 'var(--bg-primary)',
                          color: 'var(--text-secondary)',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        Line {issue.line}
                      </span>
                    )}
                  </div>
                  {issue.auto_fixable && (
                    <button
                      onClick={() => handleFixSingle(issue.check)}
                      disabled={healthFix.isPending}
                      className="flex-shrink-0 p-1.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      title={issue.fix || 'Auto-fix this issue'}
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                    >
                      <Wrench size={12} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
