import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Settings,
  Plug,
  Subtitles,
  Globe,
  Zap,
  Languages,
  Bell,
  Shield,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useConfig } from '@/hooks/useApi'

interface SettingsCategory {
  readonly id: string
  readonly icon: LucideIcon
  readonly titleKey: string
  readonly descKey: string
  readonly badge: string
}

const CATEGORIES: readonly SettingsCategory[] = [
  {
    id: 'general',
    icon: Settings,
    titleKey: 'settings.categories.general.title',
    descKey: 'settings.categories.general.description',
    badge: 'General',
  },
  {
    id: 'connections',
    icon: Plug,
    titleKey: 'settings.categories.connections.title',
    descKey: 'settings.categories.connections.description',
    badge: 'Connections',
  },
  {
    id: 'subtitles',
    icon: Subtitles,
    titleKey: 'settings.categories.subtitles.title',
    descKey: 'settings.categories.subtitles.description',
    badge: 'Subtitles',
  },
  {
    id: 'providers',
    icon: Globe,
    titleKey: 'settings.categories.providers.title',
    descKey: 'settings.categories.providers.description',
    badge: 'Providers',
  },
  {
    id: 'automation',
    icon: Zap,
    titleKey: 'settings.categories.automation.title',
    descKey: 'settings.categories.automation.description',
    badge: 'Automation',
  },
  {
    id: 'translation',
    icon: Languages,
    titleKey: 'settings.categories.translation.title',
    descKey: 'settings.categories.translation.description',
    badge: 'AI',
  },
  {
    id: 'notifications',
    icon: Bell,
    titleKey: 'settings.categories.notifications.title',
    descKey: 'settings.categories.notifications.description',
    badge: 'Channels',
  },
  {
    id: 'system',
    icon: Shield,
    titleKey: 'settings.categories.system.title',
    descKey: 'settings.categories.system.description',
    badge: 'System',
  },
]

const CATEGORY_FALLBACKS: Record<string, { title: string; description: string }> = {
  general: { title: 'General', description: 'Language, paths, logging' },
  connections: { title: 'Connections', description: 'Sonarr, Radarr, Media Servers' },
  subtitles: { title: 'Subtitles', description: 'Scoring, format, cleanup' },
  providers: { title: 'Providers', description: 'Download sources' },
  automation: { title: 'Automation', description: 'Scheduling, upgrades' },
  translation: { title: 'Translation', description: 'AI translation backends' },
  notifications: { title: 'Notifications', description: 'Channels, templates' },
  system: { title: 'System', description: 'Security, backup, logs' },
}

interface SettingsGridProps {
  readonly disabledCategories?: readonly string[]
  readonly className?: string
}

interface CategoryCardProps {
  readonly category: SettingsCategory
  readonly disabled: boolean
  readonly isTranslationCard?: boolean
  readonly translationEnabled?: boolean
  readonly onClick: () => void
}

function CategoryCard({
  category,
  disabled,
  isTranslationCard = false,
  translationEnabled = false,
  onClick,
}: CategoryCardProps) {
  const { t } = useTranslation('common')
  const Icon = category.icon
  const fallback = CATEGORY_FALLBACKS[category.id]

  const rawTitle = t(category.titleKey)
  const rawDesc = t(category.descKey)
  const title = rawTitle === category.titleKey ? fallback.title : rawTitle
  const description = rawDesc === category.descKey ? fallback.description : rawDesc

  return (
    <div
      data-testid={`settings-card-${category.id}`}
      data-disabled={disabled ? 'true' : undefined}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={disabled ? undefined : onClick}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onClick()
        }
      }}
      className={cn(
        'relative flex flex-col gap-3 rounded-xl cursor-pointer',
        'border border-[var(--border)] bg-[var(--bg-surface)]',
        'transition-all duration-200',
        'hover:-translate-y-0.5 hover:border-[var(--accent)]',
        'focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1',
        disabled && 'opacity-40 pointer-events-none cursor-default',
      )}
      style={{ padding: 22 }}
      onMouseEnter={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 20px rgba(0,0,0,0.2)'
        }
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
      }}
    >
      {/* Top-right: feature-tag for translation card, plain muted text for others */}
      {isTranslationCard ? (
        <div
          data-testid={`settings-card-badge-${category.id}`}
          className="absolute"
          style={{
            top: 18,
            right: 18,
            fontSize: 9,
            fontWeight: 600,
            padding: '2px 7px',
            borderRadius: 999,
            backgroundColor: translationEnabled ? 'var(--success-bg)' : 'var(--accent-bg)',
            color: translationEnabled ? 'var(--success)' : 'var(--accent)',
          }}
        >
          {translationEnabled ? 'Enabled' : 'Requires Enable'}
        </div>
      ) : (
        <div
          data-testid={`settings-card-badge-${category.id}`}
          className="absolute"
          style={{
            top: 18,
            right: 18,
            fontSize: 10,
            fontWeight: 500,
            color: 'var(--text-muted)',
          }}
        >
          {category.badge}
        </div>
      )}

      {/* Icon box */}
      <div
        data-testid={`settings-card-icon-${category.id}`}
        className="flex items-center justify-center rounded-[10px] shrink-0"
        style={{
          width: 40,
          height: 40,
          backgroundColor: 'var(--accent-bg)',
        }}
      >
        <Icon size={18} style={{ color: 'var(--accent)' }} />
      </div>

      {/* Text */}
      <div className="flex flex-col gap-1">
        <span
          data-testid={`settings-card-title-${category.id}`}
          className="font-semibold leading-tight"
          style={{ fontSize: 15, color: 'var(--text-primary)' }}
        >
          {title}
        </span>
        <span
          data-testid={`settings-card-desc-${category.id}`}
          className="leading-snug"
          style={{ fontSize: 11, color: 'var(--text-muted)' }}
        >
          {description}
        </span>
      </div>
    </div>
  )
}

export function SettingsGrid({ disabledCategories = [], className }: SettingsGridProps) {
  const navigate = useNavigate()
  const { data: config } = useConfig()

  const translationEnabled = Boolean(config?.translation_enabled)

  return (
    <div className="flex flex-col gap-0">
      {/* Card grid */}
      <div
        data-testid="settings-grid"
        className={cn(className)}
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
          gap: 12,
        }}
      >
        {CATEGORIES.map((category) => {
          const isTranslationCard = category.id === 'translation'
          const isDisabled = disabledCategories.includes(category.id) ||
            (isTranslationCard && !translationEnabled)
          return (
            <CategoryCard
              key={category.id}
              category={category}
              disabled={isDisabled}
              isTranslationCard={isTranslationCard}
              translationEnabled={translationEnabled}
              onClick={() => navigate(`/settings/${category.id}`)}
            />
          )
        })}
      </div>
    </div>
  )
}
