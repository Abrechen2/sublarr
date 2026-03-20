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
  readonly onClick: () => void
}

function CategoryCard({ category, disabled, onClick }: CategoryCardProps) {
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
        'relative flex flex-col gap-3 rounded-xl p-4 cursor-pointer',
        'border border-[var(--border)] bg-[var(--bg-surface)]',
        'transition-all duration-200',
        'hover:-translate-y-0.5 hover:border-[var(--accent)] hover:shadow-md',
        'focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1',
        disabled && 'opacity-40 pointer-events-none cursor-default',
      )}
    >
      {/* Top-right badge */}
      <div
        data-testid={`settings-card-badge-${category.id}`}
        className="absolute top-3 right-3 px-2 py-0.5 rounded-md text-[10px] font-medium"
        style={{
          backgroundColor: 'var(--accent-bg)',
          color: 'var(--accent)',
        }}
      >
        {category.badge}
      </div>

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
          style={{ fontSize: 11, color: 'var(--text-secondary)' }}
        >
          {description}
        </span>
      </div>
    </div>
  )
}

export function SettingsGrid({ disabledCategories = [], className }: SettingsGridProps) {
  const navigate = useNavigate()

  return (
    <div
      data-testid="settings-grid"
      className={cn(
        'grid gap-4',
        'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
        className,
      )}
    >
      {CATEGORIES.map((category) => (
        <CategoryCard
          key={category.id}
          category={category}
          disabled={disabledCategories.includes(category.id)}
          onClick={() => navigate(`/settings/${category.id}`)}
        />
      ))}
    </div>
  )
}
