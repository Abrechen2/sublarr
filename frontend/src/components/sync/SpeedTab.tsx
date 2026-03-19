/**
 * Speed tab — multiply subtitle timing by a speed factor.
 */

interface SpeedTabProps {
  speedFactor: number
  onSpeedChange: (value: number) => void
}

export function SpeedTab({ speedFactor, onSpeedChange }: SpeedTabProps) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        Speed Factor
      </label>
      <div className="space-y-2">
        <input
          type="number"
          value={speedFactor}
          onChange={(e) => onSpeedChange(Number(e.target.value))}
          min={0.5}
          max={2.0}
          step={0.01}
          className="w-full px-3 py-1.5 rounded text-sm tabular-nums text-center"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
        <div className="flex gap-2">
          {[0.95, 1.0, 1.05].map((preset) => (
            <button
              key={preset}
              onClick={() => onSpeedChange(preset)}
              className="flex-1 px-2 py-1 rounded text-xs font-medium tabular-nums transition-colors"
              style={{
                backgroundColor: speedFactor === preset ? 'var(--accent-bg)' : 'var(--bg-primary)',
                border: `1px solid ${speedFactor === preset ? 'var(--accent-dim)' : 'var(--border)'}`,
                color: speedFactor === preset ? 'var(--accent)' : 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {preset.toFixed(2)}x
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
