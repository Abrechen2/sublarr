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
        'w-[48px] hover:w-[220px] transition-[width] duration-200 ease-in-out',
        'overflow-hidden',
        'hidden md:flex'
      )}
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Logo */}
      <div className="sidebar-logo-area flex items-center py-3 shrink-0" style={{ paddingLeft: 0, paddingRight: 0, justifyContent: 'center' }}>
        <img
          data-testid="sidebar-logo"
          src="/logo-192.png"
          alt="Sublarr"
          className="shrink-0 rounded-[8px]"
          style={{ width: 28, height: 28 }}
        />
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
      <nav className="flex-1 flex flex-col px-1 py-2">
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
        className="mx-2"
        style={{ borderTop: '1px solid var(--border)' }}
      />

      {/* Bottom Items */}
      <div className="mt-auto px-1 py-2 shrink-0">
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
          'sidebar-nav-item flex items-center py-2 mb-0.5 rounded-md relative',
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
          <Icon size={20} strokeWidth={isActive ? 2.2 : 1.8} className="shrink-0" />
          <span className="sidebar-label text-[13px] font-medium truncate opacity-0 transition-opacity duration-200">
            {label}
          </span>
          {badgeCount > 0 && (
            <span
              data-testid="activity-badge"
              className="sidebar-label ml-auto text-[10px] font-bold rounded-full opacity-0 transition-opacity duration-200"
              style={{
                backgroundColor: 'var(--warning)',
                color: '#000',
                padding: '1px 6px',
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
