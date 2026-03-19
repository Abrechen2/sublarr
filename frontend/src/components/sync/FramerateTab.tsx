/**
 * Framerate tab — convert subtitle timing between frame rates.
 */

const COMMON_FRAMERATES = [23.976, 24, 25, 29.97, 30]

interface FramerateTabProps {
  inFps: number
  outFps: number
  onInFpsChange: (value: number) => void
  onOutFpsChange: (value: number) => void
}

export function FramerateTab({ inFps, outFps, onInFpsChange, onOutFpsChange }: FramerateTabProps) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>
            Source FPS
          </label>
          <select
            value={inFps}
            onChange={(e) => onInFpsChange(Number(e.target.value))}
            className="w-full px-3 py-1.5 rounded text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {COMMON_FRAMERATES.map((fps) => (
              <option key={fps} value={fps}>
                {fps}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>
            Target FPS
          </label>
          <select
            value={outFps}
            onChange={(e) => onOutFpsChange(Number(e.target.value))}
            className="w-full px-3 py-1.5 rounded text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {COMMON_FRAMERATES.map((fps) => (
              <option key={fps} value={fps}>
                {fps}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
