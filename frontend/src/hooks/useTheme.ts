import { useState, useEffect } from 'react'

type Theme = 'dark' | 'light' | 'system'

function getResolvedDark(theme: Theme): boolean {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  return theme === 'dark'
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem('sublarr-theme') as Theme) || 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    const isDark = getResolvedDark(theme)
    root.classList.toggle('dark', isDark)

    if (theme === 'system') {
      localStorage.removeItem('sublarr-theme')
    } else {
      localStorage.setItem('sublarr-theme', theme)
    }

    // Listen for OS preference changes when in system mode
    if (theme === 'system') {
      const mql = window.matchMedia('(prefers-color-scheme: dark)')
      const handler = (e: MediaQueryListEvent) => {
        root.classList.toggle('dark', e.matches)
      }
      mql.addEventListener('change', handler)
      return () => mql.removeEventListener('change', handler)
    }
  }, [theme])

  const setTheme = (t: Theme) => {
    setThemeState(t)
  }

  return { theme, setTheme }
}
