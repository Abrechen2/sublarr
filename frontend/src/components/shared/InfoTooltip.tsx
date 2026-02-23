import { useState, useRef, useEffect } from 'react'
import { Info } from 'lucide-react'

interface InfoTooltipProps {
  text: string
  className?: string
}

export function InfoTooltip({ text, className = '' }: InfoTooltipProps) {
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!visible) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setVisible(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [visible])

  return (
    <span className={`relative inline-flex items-center ${className}`}>
      <button
        ref={ref}
        type="button"
        aria-label="More information"
        className="inline-flex items-center justify-center w-4 h-4 rounded-full transition-colors duration-150 focus:outline-none cursor-pointer"
        style={{ color: visible ? 'var(--accent)' : 'var(--text-muted)' }}
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible((v) => !v)}
      >
        <Info size={15} />
      </button>

      {visible && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-[280px] rounded-md px-3 py-2 text-xs leading-relaxed shadow-lg pointer-events-none"
          style={{
            transform: 'translateX(-50%)',
            backgroundColor: 'var(--bg-elevated, var(--bg-surface))',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          {/* Arrow — outer border */}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0"
            style={{
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid var(--border)',
            }}
          />
          {/* Arrow — inner fill */}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0"
            style={{
              marginTop: '-1px',
              borderLeft: '4px solid transparent',
              borderRight: '4px solid transparent',
              borderTop: '4px solid var(--bg-elevated, var(--bg-surface))',
            }}
          />
          {text}
        </span>
      )}
    </span>
  )
}
