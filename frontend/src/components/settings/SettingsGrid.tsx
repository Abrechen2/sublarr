import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { EnableTranslationModal } from './EnableTranslationModal'
import {
  Settings,
  Plug,
  Subtitles,
  Globe,
  Zap,
  Languages,
  Bell,
  Shield,
  Heart,
  Trash2,
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
  {
    id: 'cleanup',
    icon: Trash2,
    titleKey: 'settings.categories.cleanup.title',
    descKey: 'settings.categories.cleanup.description',
    badge: 'Cleanup',
  },
  {
    id: 'about',
    icon: Heart,
    titleKey: 'settings.categories.about.title',
    descKey: 'settings.categories.about.description',
    badge: 'About',
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
  cleanup: { title: 'Cleanup', description: 'Language filters, format upgrades, orphan removal' },
  about: { title: 'About', description: 'Version, GitHub, donate' },
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
  readonly onDisabledClick?: () => void
}

function CategoryCard({
  category,
  disabled,
  isTranslationCard = false,
  translationEnabled = false,
  onClick,
  onDisabledClick,
}: CategoryCardProps) {
  const { t } = useTranslation('common')
  const Icon = category.icon
  const fallback = CATEGORY_FALLBACKS[category.id]

  const rawTitle = t(category.titleKey)
  const rawDesc = t(category.descKey)
  const title = rawTitle === category.titleKey ? fallback.title : rawTitle
  const description = rawDesc === category.descKey ? fallback.description : rawDesc

  const isSoftDisabled = !!onDisabledClick

  return (
    <div
      data-testid={`settings-card-${category.id}`}
      data-disabled={disabled ? 'true' : undefined}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || isSoftDisabled}
      onClick={disabled ? undefined : (isSoftDisabled ? onDisabledClick : onClick)}
      onKeyDown={(e) => {
        if (disabled) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          if (isSoftDisabled) { onDisabledClick?.() } else { onClick() }
        }
      }}
      className={cn(
        'relative flex flex-col gap-3 rounded-xl cursor-pointer',
        'border border-[var(--border)] bg-[var(--bg-surface)]',
        'transition-all duration-200',
        !disabled && !isSoftDisabled && 'hover:-translate-y-0.5 hover:border-[var(--accent)]',
        'focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1',
        disabled && 'opacity-40 pointer-events-none cursor-default',
        isSoftDisabled && 'opacity-50',
      )}
      style={{ padding: 22 }}
      onMouseEnter={(e) => {
        if (!disabled && !isSoftDisabled) {
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
          className="absolute flex items-center gap-1"
          style={{ top: 18, right: 18 }}
        >
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: 999,
              backgroundColor: 'var(--warning-bg, rgba(245,158,11,0.15))',
              color: 'var(--warning, #f59e0b)',
            }}
          >
            BETA
          </span>
          <span
            style={{
              fontSize: 9,
              fontWeight: 600,
              padding: '2px 7px',
              borderRadius: 999,
              backgroundColor: translationEnabled ? 'var(--success-bg)' : 'var(--accent-bg)',
              color: translationEnabled ? 'var(--success)' : 'var(--accent)',
            }}
          >
            {translationEnabled ? t('status.enabled') : t('actions.enable')}
          </span>
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
  const [showEnableModal, setShowEnableModal] = useState(false)

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
          const isSystemDisabled = disabledCategories.includes(category.id)
          const isTranslationDisabled = isTranslationCard && !translationEnabled
          return (
            <CategoryCard
              key={category.id}
              category={category}
              disabled={isSystemDisabled}
              isTranslationCard={isTranslationCard}
              translationEnabled={translationEnabled}
              onClick={() => navigate(`/settings/${category.id}`)}
              onDisabledClick={isTranslationDisabled ? () => setShowEnableModal(true) : undefined}
            />
          )
        })}
      </div>
      {showEnableModal && (
        <EnableTranslationModal onClose={() => setShowEnableModal(false)} />
      )}
    </div>
  )
}
