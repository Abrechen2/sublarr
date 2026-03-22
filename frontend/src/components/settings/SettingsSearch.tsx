/**
 * SettingsSearch — search bar for the settings overview page.
 *
 * Renders a search input with dropdown results that navigate to the
 * matching settings category page on click.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { searchSettings, type SettingsEntry } from './settingsRegistry'

interface SettingsSearchProps {
  readonly className?: string
}

export function SettingsSearch({ className }: SettingsSearchProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<readonly SettingsEntry[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Update results when query changes
  useEffect(() => {
    const found = searchSettings(query)
    setResults(found)
    setActiveIndex(-1)
    setIsOpen(query.length > 0)
  }, [query])

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = useCallback(
    (entry: SettingsEntry) => {
      navigate(entry.route)
      setQuery('')
      setIsOpen(false)
      inputRef.current?.blur()
    },
    [navigate],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isOpen || results.length === 0) return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((prev) => (prev < results.length - 1 ? prev + 1 : 0))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : results.length - 1))
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault()
        handleSelect(results[activeIndex])
      } else if (e.key === 'Escape') {
        setIsOpen(false)
        inputRef.current?.blur()
      }
    },
    [isOpen, results, activeIndex, handleSelect],
  )

  return (
    <div
      ref={containerRef}
      data-testid="settings-search"
      className={cn('relative', className)}
    >
      {/* Search input */}
      <div
        className="flex items-center gap-2 rounded-lg border px-3 py-2"
        style={{
          backgroundColor: 'var(--bg-primary)',
          borderColor: 'var(--border)',
        }}
      >
        <Search size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <input
          ref={inputRef}
          data-testid="settings-search-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (query.length > 0 && results.length > 0) setIsOpen(true)
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search settings..."
          className="flex-1 bg-transparent text-[13px] outline-none"
          style={{ color: 'var(--text-primary)' }}
          aria-label="Search settings"
          aria-expanded={isOpen}
          aria-controls="settings-search-results"
          role="combobox"
          aria-autocomplete="list"
        />
        {query && (
          <button
            data-testid="settings-search-clear"
            type="button"
            onClick={() => {
              setQuery('')
              inputRef.current?.focus()
            }}
            className="flex items-center justify-center"
            aria-label="Clear search"
          >
            <X size={14} style={{ color: 'var(--text-muted)' }} />
          </button>
        )}
      </div>

      {/* Results dropdown */}
      {isOpen && results.length > 0 && (
        <div
          id="settings-search-results"
          data-testid="settings-search-results"
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 rounded-lg border shadow-lg z-50 max-h-[300px] overflow-y-auto"
          style={{
            backgroundColor: 'var(--bg-surface)',
            borderColor: 'var(--border)',
          }}
        >
          {results.map((entry, i) => (
            <div
              key={entry.id}
              data-testid={`settings-search-result-${entry.id}`}
              role="option"
              aria-selected={i === activeIndex}
              onClick={() => handleSelect(entry)}
              onMouseEnter={() => setActiveIndex(i)}
              className={cn(
                'flex items-center justify-between px-3 py-2 cursor-pointer text-[13px]',
                'transition-colors duration-100',
                i === activeIndex && 'bg-[var(--bg-surface-hover)]',
              )}
              style={{ color: 'var(--text-primary)' }}
            >
              <span>{entry.label}</span>
              <span
                className="text-[11px] px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: 'var(--accent-bg)',
                  color: 'var(--accent)',
                }}
              >
                {entry.category}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* No results */}
      {isOpen && query.length > 0 && results.length === 0 && (
        <div
          data-testid="settings-search-empty"
          className="absolute top-full left-0 right-0 mt-1 rounded-lg border px-3 py-3 text-[13px]"
          style={{
            backgroundColor: 'var(--bg-surface)',
            borderColor: 'var(--border)',
            color: 'var(--text-muted)',
          }}
        >
          No settings found
        </div>
      )}
    </div>
  )
}
