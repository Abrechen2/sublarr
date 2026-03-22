import { useTranslation } from 'react-i18next'
import { useHealth } from '@/hooks/useApi'
import { useScannerStatus } from '@/hooks/useWantedApi'

export function StatusBar() {
  const { t } = useTranslation('common')
  const { data: health } = useHealth()
  const { data: scannerStatus } = useScannerStatus()

  const isHealthy = health?.status === 'healthy'
  const isScanning = scannerStatus?.is_scanning ?? false
  const isSearching = scannerStatus?.is_searching ?? false
  const isAutomationActive = isScanning || isSearching

  const automationLabel = isAutomationActive
    ? t('status.automation_active', 'Automation: active')
    : t('status.automation_paused', 'Automation: paused')

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
      <div
        className="h-3"
        style={{ borderLeft: '1px solid var(--border)' }}
      />

      {/* Automation status */}
      <span data-testid="status-bar-automation">
        {automationLabel}
      </span>

      {/* Separator */}
      <div
        className="h-3"
        style={{ borderLeft: '1px solid var(--border)' }}
      />

      {/* Version */}
      <span data-testid="status-bar-version">
        v{health?.version ?? '...'}
      </span>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Scanner status */}
      {isAutomationActive && (
        <span data-testid="status-bar-scanning" className="flex items-center gap-1">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: 'var(--accent)',
              animation: 'dotGlow 1.5s ease-in-out infinite',
            }}
          />
          {isScanning
            ? t('status.scanning', 'Scanning...')
            : t('status.searching', 'Searching...')}
        </span>
      )}
    </div>
  )
}
