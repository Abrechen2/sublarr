import { useState, useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useHealth, useUpdateInfo } from '@/hooks/useApi'
import { useScannerStatus, useWantedBatchStatus, useWantedBatchProbeStatus } from '@/hooks/useWantedApi'
import { useProviderHealth } from '@/hooks/useProvidersApi'

export function StatusBar() {
  const { t } = useTranslation('common')
  const { data: health } = useHealth()
  const { data: updateInfo } = useUpdateInfo()
  const { data: scannerStatus } = useScannerStatus()
  const { data: batchSearch } = useWantedBatchStatus()
  const { data: batchProbe } = useWantedBatchProbeStatus()
  const { data: providerHealth } = useProviderHealth()
  const [popoverOpen, setPopoverOpen] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  const isHealthy = health?.status === 'healthy'
  const isScanning = scannerStatus?.is_scanning ?? false
  const isSearching = scannerStatus?.is_searching ?? false
  const isBatchSearching = batchSearch?.running ?? false
  const isBatchExtracting = batchProbe?.running ?? false
  const isAutomationActive = isScanning || isSearching || isBatchSearching || isBatchExtracting
  const hasUpdate = updateInfo?.available === true

  const throttledProviders = useMemo(() => {
    if (!providerHealth) return []
    return Object.entries(providerHealth)
      .filter(([, v]) => v.circuit_state === 'open' || v.rate_limited)
      .map(([name]) => name)
  }, [providerHealth])

  const automationLabel = isAutomationActive
    ? t('status.automation_active', 'Automation: active')
    : t('status.automation_paused', 'Automation: paused')

  useEffect(() => {
    if (!popoverOpen) return
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [popoverOpen])

  return (
    <div
      data-testid="status-bar"
      className="fixed bottom-0 left-0 right-0 z-30 hidden md:flex items-center"
      style={{
        height: 26,
        backgroundColor: 'var(--bg-primary)',
        borderTop: '1px solid var(--border)',
        marginLeft: 'var(--sidebar-width, 60px)',
        padding: '0 14px',
        gap: '14px',
        fontSize: 10,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {/* Health status dot */}
      <div className="flex items-center gap-1.5">
        <div
          data-testid="status-bar-health"
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{
            backgroundColor: isHealthy ? 'var(--success)' : 'var(--error)',
          }}
        />
        <span>{isHealthy ? t('app.online', 'Online') : t('app.offline', 'Offline')}</span>
      </div>

      {/* Separator */}
      <div className="h-3" style={{ borderLeft: '1px solid var(--border)' }} />

      {/* Automation status */}
      <span data-testid="status-bar-automation">{automationLabel}</span>

      {/* Separator */}
      <div className="h-3" style={{ borderLeft: '1px solid var(--border)' }} />

      {/* Version */}
      <div className="relative" ref={popoverRef}>
        {hasUpdate ? (
          <button
            data-testid="status-bar-version"
            onClick={() => setPopoverOpen((o) => !o)}
            className="flex items-center gap-1 cursor-pointer"
            style={{
              color: 'rgb(251,191,36)',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              background: 'none',
              border: 'none',
              padding: 0,
            }}
          >
            <span
              data-testid="status-bar-update-dot"
              className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
              style={{ backgroundColor: 'rgb(251,191,36)' }}
            />
            v{health?.version ?? '...'}
          </button>
        ) : (
          <span data-testid="status-bar-version">
            v{health?.version ?? '...'}
          </span>
        )}

        {hasUpdate && popoverOpen && (
          <div
            data-testid="status-bar-update-popover"
            className="absolute bottom-full mb-2 left-0 rounded shadow-lg"
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              padding: '8px 10px',
              fontSize: 11,
              minWidth: 200,
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-primary)',
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ color: 'rgb(251,191,36)', fontWeight: 600, marginBottom: 4 }}>
              ↑ v{updateInfo?.latest} {t('update.available')}
            </div>
            <a
              href={updateInfo?.url ?? '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--accent)', textDecoration: 'none' }}
            >
              {t('update.view_release')}
            </a>
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Throttled providers warning */}
      {throttledProviders.length > 0 && (
        <span
          data-testid="status-bar-throttled"
          className="flex items-center gap-1"
          title={throttledProviders.join(', ')}
        >
          <span
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{ backgroundColor: 'var(--warning)' }}
          />
          {t('status.providers_throttled', {
            count: throttledProviders.length,
            defaultValue: '{{count}} provider(s) throttled',
          })}
        </span>
      )}

      {/* Scanner / batch status */}
      {isAutomationActive && (
        <span data-testid="status-bar-scanning" className="flex items-center gap-1">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: 'var(--accent)',
              animation: 'dotGlow 1.5s ease-in-out infinite',
            }}
          />
          {isBatchExtracting
            ? t('status.extracting', 'Extracting...')
            : isBatchSearching
              ? t('status.batch_searching', 'Batch search...')
              : isScanning
                ? t('status.scanning', 'Scanning...')
                : t('status.searching', 'Searching...')}
        </span>
      )}
    </div>
  )
}
