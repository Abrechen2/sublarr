import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LayoutDashboard, BookOpen, Bell, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'
import { useWantedSummary } from '@/hooks/useWantedApi'
import { ThemeToggle } from '@/components/shared/ThemeToggle'

interface NavItem {
  readonly to: string
  readonly labelKey: string
  readonly icon: typeof LayoutDashboard
  readonly testId: string
  readonly showBadge?: boolean
}

const mainNavItems: readonly NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, testId: 'nav-link-dashboard' },
  { to: '/library', labelKey: 'nav.library', icon: BookOpen, testId: 'nav-link-library' },
  { to: '/activity', labelKey: 'nav.activity', icon: Bell, testId: 'nav-link-activity', showBadge: true },
] as const

const bottomNavItems: readonly NavItem[] = [
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, testId: 'nav-link-settings' },
] as const

export function IconSidebar() {
  const { t } = useTranslation('common')
  const { data: health } = useHealth()
  const { data: wantedSummary } = useWantedSummary()

  const wantedCount = wantedSummary?.total ?? 0

  return (
    <aside
      data-testid="icon-sidebar"
      className={cn(
        'icon-sidebar',
        'fixed left-0 top-0 h-screen z-40 flex flex-col',
        'w-[60px] hover:w-[220px] transition-[width] duration-200 ease-in-out',
        'overflow-hidden',
        'hidden md:flex'
      )}
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-3 py-3.5 shrink-0">
        <div
          data-testid="sidebar-logo"
          className="flex items-center justify-center shrink-0 rounded-md font-bold text-white"
          style={{
            width: 36,
            height: 36,
            background: 'linear-gradient(135deg, #0f9bb5, #1DB8D4)',
            fontSize: 18,
          }}
        >
          S
        </div>
        <div className="sidebar-label flex flex-col min-w-0 opacity-0 transition-opacity duration-200">
          <span
            className="text-base font-bold tracking-tight truncate"
            style={{ color: 'var(--accent)' }}
          >
            Sublarr
          </span>
          <span
            data-testid="sidebar-version"
            className="text-[10px] truncate"
            style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
          >
            v{health?.version ?? '...'}
          </span>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 flex flex-col px-2 py-2">
        {mainNavItems.map((item) => (
          <SidebarNavItem
            key={item.to}
            item={item}
            label={t(item.labelKey)}
            badgeCount={item.showBadge ? wantedCount : 0}
          />
        ))}
      </nav>

      {/* Separator */}
      <div
        data-testid="sidebar-separator"
        className="mx-3"
        style={{ borderTop: '1px solid var(--border)' }}
      />

      {/* Bottom Items */}
      <div className="mt-auto px-2 py-2 shrink-0">
        {bottomNavItems.map((item) => (
          <SidebarNavItem
            key={item.to}
            item={item}
            label={t(item.labelKey)}
            badgeCount={0}
          />
        ))}
        <div className="flex items-center justify-center py-1">
          <ThemeToggle />
        </div>
      </div>
    </aside>
  )
}

interface SidebarNavItemProps {
  readonly item: NavItem
  readonly label: string
  readonly badgeCount: number
}

function SidebarNavItem({ item, label, badgeCount }: SidebarNavItemProps) {
  const { to, icon: Icon, testId } = item

  return (
    <NavLink
      to={to}
      end={to === '/'}
      data-testid={testId}
      aria-label={label}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 px-3 py-2 mb-0.5 rounded-md relative',
          'transition-colors duration-100',
          !isActive && 'hover:bg-[rgba(255,255,255,0.04)]'
        )
      }
      style={({ isActive }) => ({
        color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
      })}
    >
      {({ isActive }) => (
        <>
          {/* Active indicator bar */}
          {isActive && (
            <div
              className="absolute left-0 top-[6px] bottom-[6px] w-[3px] rounded-r-sm"
              style={{ backgroundColor: 'var(--accent)' }}
            />
          )}
          <Icon size={24} strokeWidth={isActive ? 2.2 : 1.8} className="shrink-0" />
          <span className="sidebar-label text-[13px] font-medium truncate opacity-0 transition-opacity duration-200">
            {label}
          </span>
          {badgeCount > 0 && (
            <span
              data-testid="activity-badge"
              className="sidebar-label ml-auto text-[11px] font-semibold px-1.5 py-0.5 rounded-full opacity-0 transition-opacity duration-200"
              style={{
                backgroundColor: 'var(--warning-bg)',
                color: 'var(--warning)',
              }}
            >
              {badgeCount > 99 ? '99+' : badgeCount}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}
