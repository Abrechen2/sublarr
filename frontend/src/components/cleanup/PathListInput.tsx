import { useState } from 'react'

interface PathListInputProps {
  label: string
  placeholder: string
  hint: string
  value: string[]
  onChange: (paths: string[]) => void
}

/** Comma-separated list of media-path-relative subfolders, stored as string[].
 *
 * Local draft state keeps half-typed input (trailing commas, spaces) intact
 * while typing; the parsed list is committed on change so the rule config
 * only ever holds clean entries.
 */
export function PathListInput({ label, placeholder, hint, value, onChange }: PathListInputProps) {
  const [draft, setDraft] = useState(value.join(', '))

  const commit = (raw: string) => {
    setDraft(raw)
    const paths = raw
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean)
    onChange(paths)
  }

  return (
    <div className="mt-4">
      <div
        className="text-[10px] font-semibold uppercase tracking-wider mb-2"
        style={{ color: 'var(--text-muted)' }}
      >
        {label}
      </div>
      <input
        type="text"
        value={draft}
        placeholder={placeholder}
        onChange={(e) => commit(e.target.value)}
        className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none"
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
        }}
      />
      <div className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>
        {hint}
      </div>
    </div>
  )
}
