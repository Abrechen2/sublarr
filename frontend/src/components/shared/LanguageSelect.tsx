import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { useSupportedLanguages } from '@/hooks/useApi'

interface LanguageSelectProps {
  value: string
  onChange: (code: string, name: string) => void
  placeholder?: string
}

export function LanguageSelect({ value, onChange, placeholder = 'Sprache wählen…' }: LanguageSelectProps) {
  const { data: languages = [] } = useSupportedLanguages()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  const current = languages.find((l) => l.code === value)

  const filtered = search
    ? languages.filter(
        (l) =>
          l.name.toLowerCase().includes(search.toLowerCase()) ||
          l.code.toLowerCase().includes(search.toLowerCase())
      )
    : languages

  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  useEffect(() => {
    if (!open) setSearch('')
  }, [open])

  return (
    <div ref={containerRef} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm focus:outline-none"
        style={{
          backgroundColor: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          color: current ? 'var(--text-primary)' : 'var(--text-muted)',
          fontFamily: 'var(--font-mono)',
          fontSize: '13px',
        }}
      >
        <span>
          {current ? `${current.name} (${current.code})` : value || placeholder}
        </span>
        <ChevronDown size={14} style={{ color: 'var(--text-muted)', flexShrink: 0, marginLeft: '8px' }} />
      </button>

      {open && (
        <div
          className="absolute z-50 w-full mt-1 rounded-md overflow-hidden"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
          }}
        >
          {/* Search input */}
          <div className="flex items-center gap-2 px-2 py-1.5" style={{ borderBottom: '1px solid var(--border)' }}>
            <Search size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <input
              autoFocus
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Suchen…"
              className="flex-1 bg-transparent text-[12px] focus:outline-none"
              style={{ color: 'var(--text-primary)' }}
            />
          </div>

          {/* Language list */}
          <div className="overflow-y-auto" style={{ maxHeight: '200px' }}>
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                Keine Sprache gefunden
              </p>
            ) : (
              filtered.map((lang) => (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => {
                    onChange(lang.code, lang.name)
                    setOpen(false)
                  }}
                  className="w-full flex items-center justify-between px-3 py-1.5 text-left text-[12px] transition-colors"
                  style={{
                    color: lang.code === value ? 'var(--accent)' : 'var(--text-primary)',
                    backgroundColor: lang.code === value ? 'var(--accent-bg)' : 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    if (lang.code !== value) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                  }}
                  onMouseLeave={(e) => {
                    if (lang.code !== value) e.currentTarget.style.backgroundColor = 'transparent'
                  }}
                >
                  <span>{lang.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                    {lang.code}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
