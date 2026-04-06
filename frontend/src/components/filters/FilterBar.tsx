import { X, Plus, Filter } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { FilterScope, FilterGroup, FilterOperator } from '@/lib/types'
import { FilterPresetMenu } from './FilterPresetMenu'

interface FilterDef {
  key: string           // field name matching backend allowlist
  label: string         // display label
  type: 'select' | 'text' | 'number'
  options?: { value: string; label: string }[]  // for type='select'
}

interface ActiveFilter {
  key: string
  op: FilterOperator
  value: string
  label: string
}

interface FilterBarProps {
  scope: FilterScope
  filters: FilterDef[]          // available filter definitions for this page
  activeFilters: ActiveFilter[]
  onFiltersChange: (filters: ActiveFilter[]) => void
  onPresetLoad?: (conditions: FilterGroup) => void
  className?: string
}

export type { FilterDef, ActiveFilter }

export function FilterBar({ scope, filters, activeFilters, onFiltersChange, onPresetLoad, className }: FilterBarProps) {
  const { t } = useTranslation('common')
  const [addingFilter, setAddingFilter] = useState(false)
  const [pendingKey, setPendingKey] = useState('')
  const [pendingValue, setPendingValue] = useState('')
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!addingFilter) return
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setAddingFilter(false)
        setPendingKey('')
        setPendingValue('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [addingFilter])

  const removeFilter = (key: string) =>
    onFiltersChange(activeFilters.filter((f) => f.key !== key))

  const clearAll = () => onFiltersChange([])

  const addFilter = (key: string, value: string) => {
    const def = filters.find((f) => f.key === key)
    if (!def || !value) return
    const existing = activeFilters.filter((f) => f.key !== key)
    onFiltersChange([...existing, { key, op: 'eq', value, label: def.label }])
    setAddingFilter(false)
    setPendingKey('')
    setPendingValue('')
  }

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className ?? ''}`}>
      <Filter className="h-4 w-4 text-muted-foreground shrink-0" />

      {activeFilters.map((f) => (
        <span
          key={f.key}
          className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs bg-teal-500/10 text-teal-400 border border-teal-500/20"
        >
          <span className="text-muted-foreground">{f.label}:</span>
          {f.value}
          <button
            onClick={() => removeFilter(f.key)}
            className="ml-0.5 hover:text-foreground"
            aria-label={`Remove ${f.label} filter`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}

      {/* Add filter popover */}
      <div className="relative" ref={popoverRef}>
        <button
          onClick={() => setAddingFilter((v) => !v)}
          className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs border border-dashed transition-colors"
          style={{
            borderColor: addingFilter ? 'var(--accent)' : 'var(--border)',
            color: addingFilter ? 'var(--accent)' : 'var(--text-muted)',
          }}
        >
          <Plus className="h-3 w-3" />
          {t('filters.addFilter')}
        </button>
        {addingFilter && (
          <div
            style={{
              position: 'absolute',
              top: '2rem',
              left: 0,
              zIndex: 9999,
              minWidth: '200px',
              padding: '10px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--accent-dim)',
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            }}
          >
            <select
              className="w-full mb-2 text-sm rounded px-2 py-1"
              style={{
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
              value={pendingKey}
              onChange={(e) => { setPendingKey(e.target.value); setPendingValue('') }}
            >
              <option value="">{t('filters.pickField')}</option>
              {filters.map((f) => (
                <option key={f.key} value={f.key}>{f.label}</option>
              ))}
            </select>
            {pendingKey && (() => {
              const def = filters.find((f) => f.key === pendingKey)!
              return def.type === 'select' ? (
                <select
                  className="w-full text-sm rounded px-2 py-1"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                  value={pendingValue}
                  onChange={(e) => {
                    setPendingValue(e.target.value)
                    if (e.target.value) addFilter(pendingKey, e.target.value)
                  }}
                >
                  <option value="">{t('filters.pickValue')}</option>
                  {def.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              ) : (
                <input
                  type={def.type === 'number' ? 'number' : 'text'}
                  placeholder={t('filters.enterValue', { field: def.label.toLowerCase() })}
                  value={pendingValue}
                  onChange={(e) => setPendingValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && pendingValue) addFilter(pendingKey, pendingValue) }}
                  className="w-full text-sm rounded px-2 py-1 outline-none"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                  autoFocus
                />
              )
            })()}
          </div>
        )}
      </div>

      {activeFilters.length > 0 && (
        <button
          onClick={clearAll}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {t('filters.clearAll')}
        </button>
      )}

      <div className="ml-auto">
        <FilterPresetMenu
          scope={scope}
          activeFilters={activeFilters}
          onPresetLoad={onPresetLoad ?? (() => {})}
        />
      </div>
    </div>
  )
}
