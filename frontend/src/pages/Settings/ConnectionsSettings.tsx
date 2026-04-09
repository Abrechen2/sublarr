/**
 * ConnectionsSettings — settings detail page for all external service connections.
 *
 * Sections:
 * 1. Sonarr Connection   — multi-instance (sonarr_instances_json)
 * 2. Radarr Connection   — multi-instance (radarr_instances_json)
 * 3. Media Servers
 * 4. Standalone Mode
 * 5. Metadata API Keys   — TMDB, TheTVDB, cache TTL
 *
 * Sub-components are extracted to connections/ for file-size compliance.
 * All config keys, design, and SettingsSection/FormGroup patterns are unchanged.
 */
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import {
  SonarrSection,
  RadarrSection,
  MediaServersSection,
  StandaloneModeSection,
} from './connections/ConnectionsMediaServers'
import { MetadataSectionWrapper } from './connections/ConnectionsMetadata'

export function ConnectionsSettings() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title="Connections"
      subtitle="Configure external service integrations"
      breadcrumb={[
        { label: t('settings.breadcrumb.settings', 'Settings'), href: '/settings' },
        { label: 'Connections' },
      ]}
    >
      <SonarrSection />
      <RadarrSection />
      <MediaServersSection />
      <StandaloneModeSection />
      <MetadataSectionWrapper />
    </SettingsDetailLayout>
  )
}
