import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, useMatch } from 'react-router-dom'
import { Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SettingsSearchModal } from './SettingsSearchModal'

interface NavPage {
  readonly label: string
  readonly href: string
}

interface NavGroup {
  readonly label: string
  readonly pages: readonly NavPage[]
}

function useNavGroups(): readonly NavGroup[] {
  const { t } = useTranslation('common')

  const groups: NavGroup[] = [
    {
      label: t('settings.categories.general.title', 'Allgemein'),
      pages: [
        { label: t('settings.nav.app_interface', 'App & Oberfläche'), href: '/settings/general' },
      ],
    },
    {
      label: t('settings.categories.connections.title', 'Verbindungen'),
      pages: [
        { label: t('settings.nav.arr_media', 'Sonarr, Radarr & Medienserver'), href: '/settings/connections' },
        { label: t('settings.nav.metadata', 'Metadaten'), href: '/settings/connections/metadata' },
      ],
    },
    {
      label: t('settings.categories.subtitles.title', 'Untertitel'),
      pages: [
        { label: t('settings.nav.languages', 'Sprachen & Profile'), href: '/settings/subtitles/languages' },
        { label: t('settings.nav.scoring', 'Scoring'), href: '/settings/subtitles/scoring' },
        { label: t('settings.nav.format_naming', 'Format & Benennung'), href: '/settings/subtitles/format' },
        { label: t('settings.nav.cleanup', 'Bereinigung'), href: '/settings/cleanup' },
        { label: t('settings.nav.stream_management', 'Stream-Verwaltung'), href: '/settings/subtitles/stream-management' },
      ],
    },
    {
      label: t('settings.categories.providers.title', 'Provider'),
      pages: [
        { label: t('settings.nav.providers_list', 'Provider & Zugangsdaten'), href: '/settings/providers' },
        { label: t('settings.nav.transcription', 'Transkription'), href: '/settings/providers/transcription' },
      ],
    },
    {
      label: t('settings.categories.automation.title', 'Automatisierung'),
      pages: [
        { label: t('settings.nav.search_scan', 'Suche, Scan & Upgrades'), href: '/settings/automation' },
        { label: t('settings.nav.post_processing', 'Post-Processing'), href: '/settings/automation/post-processing' },
        { label: t('settings.nav.subtitle_automation', 'Untertitel-Automation'), href: '/settings/automation/subtitle' },
      ],
    },
  ]

  // Always show the Translation group so the feature is reachable even when
  // it is currently disabled — the page itself carries the enable control.
  groups.push({
    label: t('settings.categories.translation.title', 'Übersetzung'),
    pages: [
      { label: t('settings.nav.translation_backends', 'Backends & Glossar'), href: '/settings/translation' },
      { label: t('settings.nav.translation_cost', 'Kosten & Memory'), href: '/settings/translation/cost-memory' },
      { label: t('settings.nav.translation_queue', 'Queue'), href: '/settings/translation/queue' },
    ],
  })

  groups.push(
    {
      label: t('settings.categories.notifications.title', 'Benachrichtigungen'),
      pages: [
        { label: t('settings.nav.channels_templates', 'Kanäle & Vorlagen'), href: '/settings/notifications' },
      ],
    },
    {
      label: t('settings.categories.system.title', 'System'),
      pages: [
        { label: t('settings.nav.security_backup', 'Sicherheit, Backup & Logs'), href: '/settings/system' },
        { label: t('settings.nav.hooks_webhooks', 'Hooks & Webhooks'), href: '/settings/system/hooks' },
        { label: t('settings.nav.scheduler', 'Scheduler'), href: '/settings/system/scheduler' },
        { label: t('settings.nav.subtitle_health', 'Untertitel-Gesundheit'), href: '/settings/system/subtitle-health' },
        { label: t('settings.nav.sync_engines', 'Sync Engines'), href: '/settings/system/sync-engines' },
      ],
    },
    {
      label: t('settings.categories.about.title', 'Über'),
      pages: [
        { label: t('settings.categories.about.title', 'Über Sublarr'), href: '/settings/about' },
      ],
    },
  )

  return groups
}

function NavPageLink({ href, label }: NavPage) {
  const match = useMatch(href)

  return (
    <NavLink
      to={href}
      className={cn(
        'block px-3 py-[6px] rounded-[6px] text-[12px] leading-snug transition-colors duration-150',
        match
          ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-medium'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)]',
      )}
    >
      {label}
    </NavLink>
  )
}

export function SettingsNav() {
  const { t: tc } = useTranslation('common')
  const groups = useNavGroups()
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <>
    <nav
      data-testid="settings-nav"
      className="shrink-0 overflow-y-auto w-full md:w-[210px] md:min-w-[210px]"
      style={{
        paddingRight: 8,
        paddingTop: 16,
        paddingBottom: 24,
      }}
    >
      {/* Search trigger */}
      <button
        onClick={() => setSearchOpen(true)}
        className="flex items-center gap-2 w-full px-3 py-2 mb-4 rounded-lg text-xs transition-colors hover:opacity-80"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border)',
          color: 'var(--text-muted)',
        }}
      >
        <Search size={12} />
        <span className="flex-1 text-left">{tc('ui.search_ellipsis')}</span>
        <kbd
          className="font-mono text-[10px] px-1 py-0.5 rounded"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          Ctrl K
        </kbd>
      </button>

      {groups.map((group) => (
        <div key={group.label} style={{ marginBottom: 20 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
              padding: '0 12px',
              marginBottom: 4,
            }}
          >
            {group.label}
          </div>
          <div className="flex flex-col gap-[2px]">
            {group.pages.map((page) => (
              <NavPageLink key={page.href} href={page.href} label={page.label} />
            ))}
          </div>
        </div>
      ))}
    </nav>
    <SettingsSearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  )
}
