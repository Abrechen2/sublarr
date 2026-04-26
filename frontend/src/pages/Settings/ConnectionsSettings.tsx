/**
 * ConnectionsSettings — settings detail page for all external service connections.
 *
 * Sections (5 — under the FormLayout 6-cap):
 * 1. Sonarr           — multi-instance (sonarr_instances_json)
 * 2. Radarr           — multi-instance (radarr_instances_json)
 * 3. Media Servers    — Plex / Jellyfin / Emby
 * 4. Standalone Mode  — file-system watcher when no *arr is configured
 * 5. Metadata API Keys — TMDB, TheTVDB, cache TTL
 *
 * Each Sonarr/Radarr/MediaServers internally manages its own instance
 * collection — they remain SettingsSection-wrapped collections rather than
 * being lifted to a page-level CollectionLayout. That intentional asymmetry
 * preserves the per-service icon / description framing the user already
 * recognises; if the multi-instance UI of any service is touched for feature
 * work, the Hybrid-Ratchet rule says it migrates to a real CollectionLayout
 * at that time.
 */
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import {
  SonarrSection,
  RadarrSection,
  MediaServersSection,
  StandaloneModeSection,
} from './connections/ConnectionsMediaServers'
import { MetadataSectionWrapper } from './connections/ConnectionsMetadata'

// Settings Template B (FormLayout). titleKey points at the SAME key that
// each XSection's <SettingsSection title=> already uses, so TOC + section
// header stay in sync (single source of truth).
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'sonarr',         titleKey: 'connections_media_servers.sonarr' },
  { id: 'radarr',         titleKey: 'connections_media_servers.radarr' },
  { id: 'media-servers',  titleKey: 'connections_media_servers.title' },
  { id: 'standalone',     titleKey: 'connections.standalone.section_title' },
  { id: 'metadata',       titleKey: 'connections_metadata.title' },
]

export function ConnectionsSettings() {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={tc('ui.connections')}
      subtitle={tc('ui.configure_external')}
      breadcrumb={[
        { label: t('settings.breadcrumb.settings', 'Settings'), href: '/settings' },
        { label: 'Connections' },
      ]}
    >
      <FormLayout sections={SECTIONS}>
        <section id="sonarr" data-testid="settings.connections.section-sonarr">
          <SonarrSection />
        </section>
        <section id="radarr" data-testid="settings.connections.section-radarr">
          <RadarrSection />
        </section>
        <section id="media-servers" data-testid="settings.connections.section-media-servers">
          <MediaServersSection />
        </section>
        <section id="standalone" data-testid="settings.connections.section-standalone">
          <StandaloneModeSection />
        </section>
        <section id="metadata" data-testid="settings.connections.section-metadata">
          <MetadataSectionWrapper />
        </section>
      </FormLayout>
    </SettingsDetailLayout>
  )
}
