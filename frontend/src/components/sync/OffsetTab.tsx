/**
 * Offset tab — shift all subtitle timestamps by N milliseconds.
 */

interface OffsetTabProps {
  offsetMs: number
  onOffsetChange: (value: number) => void
}

export function OffsetTab({ offsetMs, onOffsetChange }: OffsetTabProps) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        Offset (milliseconds)
      </label>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onOffsetChange(offsetMs - 100)}
          className="px-2 py-1 rounded text-xs font-bold"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          -100
        </button>
        <input
          type="number"
          value={offsetMs}
          onChange={(e) => onOffsetChange(Number(e.target.value))}
          className="flex-1 px-3 py-1.5 rounded text-sm tabular-nums text-center"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
        <button
          onClick={() => onOffsetChange(offsetMs + 100)}
          className="px-2 py-1 rounded text-xs font-bold"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          +100
        </button>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>ms</span>
      </div>
    </div>
  )
}
