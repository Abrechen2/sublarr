import { Moon, Sun, Monitor } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'

const themeOrder = ['dark', 'light', 'system'] as const
type Theme = (typeof themeOrder)[number]

const themeIcons: Record<Theme, typeof Moon> = {
  dark: Moon,
  light: Sun,
  system: Monitor,
}

const themeLabels: Record<Theme, string> = {
  dark: 'Dark',
  light: 'Light',
  system: 'System',
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  const cycleTheme = () => {
    const currentIndex = themeOrder.indexOf(theme)
    const nextIndex = (currentIndex + 1) % themeOrder.length
    setTheme(themeOrder[nextIndex])
  }

  const Icon = themeIcons[theme]

  return (
    <button
      onClick={cycleTheme}
      aria-label={`Theme: ${themeLabels[theme]}`}
      title={themeLabels[theme]}
      className="flex items-center justify-center rounded-md transition-colors duration-150"
      style={{
        width: 28,
        height: 28,
        color: 'var(--text-secondary)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = 'var(--accent)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      <Icon size={14} strokeWidth={2} />
    </button>
  )
}
