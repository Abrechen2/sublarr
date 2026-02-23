import { createContext, useContext, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'sublarr_show_advanced'

interface AdvancedSettingsContextValue {
  showAdvanced: boolean
  toggleAdvanced: () => void
}

const AdvancedSettingsContext = createContext<AdvancedSettingsContextValue | undefined>(undefined)

export function useAdvancedSettings() {
  const ctx = useContext(AdvancedSettingsContext)
  if (ctx === undefined) {
    throw new Error('useAdvancedSettings must be used within AdvancedSettingsProvider')
  }
  return ctx
}

interface ProviderProps {
  children: ReactNode
}

export function AdvancedSettingsProvider({ children }: ProviderProps) {
  const [showAdvanced, setShowAdvanced] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const toggleAdvanced = () => {
    setShowAdvanced((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, String(next))
      } catch {}
      return next
    })
  }

  return (
    <AdvancedSettingsContext.Provider value={{ showAdvanced, toggleAdvanced }}>
      {children}
    </AdvancedSettingsContext.Provider>
  )
}
