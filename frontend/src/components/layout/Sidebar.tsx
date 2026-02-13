import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Activity,
  Search,
  ListOrdered,
  Settings,
  ScrollText,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/wanted', label: 'Wanted', icon: Search },
  { to: '/queue', label: 'Queue', icon: ListOrdered },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/logs', label: 'Logs', icon: ScrollText },
]

export function Sidebar() {
  const { data: health } = useHealth()

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 flex flex-col"
      style={{ backgroundColor: 'var(--bg-surface)', borderRight: '1px solid var(--border)' }}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5">
        <img src="/favicon.svg" alt="Sublarr" className="w-9 h-9" />
        <span className="text-xl font-bold" style={{ color: 'var(--accent)' }}>
          Sublarr
        </span>
      </div>

      {/* Divider */}
      <div className="mx-4 mb-2" style={{ borderTop: '1px solid var(--border)' }} />

      {/* Navigation */}
      <nav className="flex-1 px-3">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors mb-0.5',
                isActive
                  ? 'text-white'
                  : 'hover:text-white'
              )
            }
            style={({ isActive }) => ({
              backgroundColor: isActive ? 'rgba(29, 184, 212, 0.15)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
            })}
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: health?.status === 'healthy' ? 'var(--success)' : 'var(--error)',
            }}
          />
          System: {health?.status === 'healthy' ? 'Healthy' : 'Unhealthy'}
        </div>
        <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          v{health?.version || '0.1.0'}
        </div>
      </div>
    </aside>
  )
}
