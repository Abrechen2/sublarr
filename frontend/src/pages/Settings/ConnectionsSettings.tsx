/**
 * ConnectionsSettings — settings detail page for all external service connections.
 *
 * Sections:
 * 1. Sonarr Connection
 * 2. Radarr Connection
 * 3. Media Servers
 * 4. API Keys
 */
import { useState, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, PlugZap, Server, KeyRound, Loader2 } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useConfig, useUpdateConfig,
  useTestSonarrInstance, useTestRadarrInstance,
} from '@/hooks/useApi'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { ConnectionCard } from '@/components/settings/ConnectionCard'
import type { ConnectionCardStatus } from '@/components/settings/ConnectionCard'

// ─── Lazy imports for heavier sub-tabs ───────────────────────────────────────
const MediaServersTab = lazy(() => import('./MediaServersTab').then(m => ({ default: m.MediaServersTab })))
const ApiKeysTab = lazy(() => import('./ApiKeysTab').then(m => ({ default: m.ApiKeysTab })))

function TabSkeleton() {
  return (
    <div className="flex items-center justify-center h-16">
      <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function configStr(data: Record<string, unknown> | undefined, key: string): string {
  return String(data?.[key] ?? '')
}

function deriveStatus(url: string): ConnectionCardStatus {
  if (!url || !url.trim()) return 'unconfigured'
  return 'unconfigured' // Actual status determined after a test
}

// ─── Sonarr Connection Section ────────────────────────────────────────────────

function SonarrSection() {
  const { t } = useTranslation('common')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const testSonarr = useTestSonarrInstance()

  const cfg = configData as Record<string, unknown> | undefined

  const [url, setUrl] = useState(() => configStr(cfg, 'sonarr_url'))
  const [apiKey, setApiKey] = useState(() => configStr(cfg, 'sonarr_api_key'))
  const [pathMapping, setPathMapping] = useState(() => configStr(cfg, 'path_mapping'))

  const [status, setStatus] = useState<ConnectionCardStatus>(() =>
    deriveStatus(configStr(cfg, 'sonarr_url')),
  )
  const [testMessage, setTestMessage] = useState<string | null>(null)

  const handleTest = () => {
    if (!url.trim()) {
      toast(t('status.not_configured'), 'error')
      return
    }
    testSonarr.mutate(
      { url: url.trim(), api_key: apiKey.trim() },
      {
        onSuccess: (result) => {
          setStatus(result.healthy ? 'connected' : 'error')
          setTestMessage(result.message)
          if (!result.healthy) toast(`Sonarr: ${result.message}`, 'error')
        },
        onError: () => {
          setStatus('error')
          setTestMessage('Connection failed')
          toast('Sonarr: Connection failed', 'error')
        },
      },
    )
  }

  const handleSave = () => {
    updateConfig.mutate(
      { sonarr_url: url, sonarr_api_key: apiKey, path_mapping: pathMapping },
      {
        onSuccess: () => toast('Sonarr settings saved'),
        onError: () => toast('Failed to save Sonarr settings', 'error'),
      },
    )
  }

  return (
    <ConnectionCard
      data-testid="sonarr-connection-card"
      abbr="SN"
      color="#5c87ca"
      name="Sonarr"
      status={status}
      url={url || undefined}
      fields={[
        {
          key: 'sonarr_url',
          label: 'Sonarr URL',
          type: 'text',
          placeholder: 'http://localhost:8989',
          value: url,
          onChange: setUrl,
        },
        {
          key: 'sonarr_api_key',
          label: 'API Key',
          type: 'password',
          placeholder: 'Settings → General → Security',
          value: apiKey,
          onChange: setApiKey,
        },
        {
          key: 'sonarr_path_mapping',
          label: 'Path Mapping',
          type: 'text',
          placeholder: '/remote=/local',
          value: pathMapping,
          onChange: setPathMapping,
        },
      ]}
      onTest={handleTest}
      onSave={handleSave}
      isTesting={testSonarr.isPending}
      isSaving={updateConfig.isPending}
      testMessage={testMessage}
    />
  )
}

// ─── Radarr Connection Section ─────────────────────────────────────────────────

function RadarrSection() {
  const { t } = useTranslation('common')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const testRadarr = useTestRadarrInstance()

  const cfg = configData as Record<string, unknown> | undefined

  const [url, setUrl] = useState(() => configStr(cfg, 'radarr_url'))
  const [apiKey, setApiKey] = useState(() => configStr(cfg, 'radarr_api_key'))

  const [status, setStatus] = useState<ConnectionCardStatus>(() =>
    deriveStatus(configStr(cfg, 'radarr_url')),
  )
  const [testMessage, setTestMessage] = useState<string | null>(null)

  const handleTest = () => {
    if (!url.trim()) {
      toast(t('status.not_configured'), 'error')
      return
    }
    testRadarr.mutate(
      { url: url.trim(), api_key: apiKey.trim() },
      {
        onSuccess: (result) => {
          setStatus(result.healthy ? 'connected' : 'error')
          setTestMessage(result.message)
          if (!result.healthy) toast(`Radarr: ${result.message}`, 'error')
        },
        onError: () => {
          setStatus('error')
          setTestMessage('Connection failed')
          toast('Radarr: Connection failed', 'error')
        },
      },
    )
  }

  const handleSave = () => {
    updateConfig.mutate(
      { radarr_url: url, radarr_api_key: apiKey },
      {
        onSuccess: () => toast('Radarr settings saved'),
        onError: () => toast('Failed to save Radarr settings', 'error'),
      },
    )
  }

  return (
    <ConnectionCard
      data-testid="radarr-connection-card"
      abbr="RD"
      color="#e8a838"
      name="Radarr"
      status={status}
      url={url || undefined}
      fields={[
        {
          key: 'radarr_url',
          label: 'Radarr URL',
          type: 'text',
          placeholder: 'http://localhost:7878',
          value: url,
          onChange: setUrl,
        },
        {
          key: 'radarr_api_key',
          label: 'API Key',
          type: 'password',
          placeholder: 'Settings → General → Security',
          value: apiKey,
          onChange: setApiKey,
        },
      ]}
      onTest={handleTest}
      onSave={handleSave}
      isTesting={testRadarr.isPending}
      isSaving={updateConfig.isPending}
      testMessage={testMessage}
    />
  )
}

// ─── Main ConnectionsSettings Page ───────────────────────────────────────────

export function ConnectionsSettings() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title="Connections"
      subtitle="Configure external service integrations"
      breadcrumb={[
        { label: 'Settings', href: '/settings' },
        { label: 'Connections' },
      ]}
    >
      {/* Sonarr */}
      <SettingsSection
        data-testid="sonarr-section"
        title="Sonarr"
        description="TV series library management and download client integration"
        icon={<Link size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <SonarrSection />
        </div>
      </SettingsSection>

      {/* Radarr */}
      <SettingsSection
        data-testid="radarr-section"
        title="Radarr"
        description="Movie library management and download client integration"
        icon={<PlugZap size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <RadarrSection />
        </div>
      </SettingsSection>

      {/* Media Servers */}
      <SettingsSection
        data-testid="media-servers-section"
        title="Media Servers"
        description="Jellyfin, Plex, and Kodi instances for library refresh notifications"
        icon={<Server size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <Suspense fallback={<TabSkeleton />}>
            <MediaServersTab />
          </Suspense>
        </div>
      </SettingsSection>

      {/* API Keys */}
      <SettingsSection
        data-testid="api-keys-section"
        title="API Keys"
        description="Manage subtitle provider API keys, test connections, and rotate secrets"
        icon={<KeyRound size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <Suspense fallback={<TabSkeleton />}>
            <ApiKeysTab />
          </Suspense>
        </div>
      </SettingsSection>
    </SettingsDetailLayout>
  )
}
