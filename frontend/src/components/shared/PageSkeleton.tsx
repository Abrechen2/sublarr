export function PageSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      {/* Page title skeleton */}
      <div className="h-8 w-48 rounded bg-gray-700/50" />

      {/* Card grid skeleton */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 rounded-lg bg-gray-700/30" />
        ))}
      </div>

      {/* Content area skeleton */}
      <div className="h-64 rounded-lg bg-gray-700/20" />
    </div>
  )
}

const pulse = 'animate-pulse rounded'
const bg1 = { backgroundColor: 'var(--bg-surface)' }
const bg2 = { backgroundColor: 'rgba(124,130,147,0.08)' }

/** Matches Library grid: grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 */
export function LibrarySkeleton() {
  return (
    <div className="space-y-4">
      <div className={`h-7 w-40 ${pulse}`} style={bg2} />
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
        {Array.from({ length: 16 }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <div className={`aspect-[2/3] w-full ${pulse}`} style={bg1} />
            <div className={`h-3 w-3/4 ${pulse}`} style={bg2} />
          </div>
        ))}
      </div>
    </div>
  )
}

/** 5-row table skeleton for History, Queue, Blacklist */
export function TableSkeleton() {
  return (
    <div className="space-y-3">
      <div className={`h-7 w-40 ${pulse}`} style={bg2} />
      <div className={`rounded-lg overflow-hidden`} style={bg1}>
        <div className="px-4 py-2.5 flex gap-4" style={{ borderBottom: '1px solid var(--border)' }}>
          {[120, 80, 60, 80].map((w, i) => (
            <div key={i} className={`h-3 ${pulse}`} style={{ ...bg2, width: w }} />
          ))}
        </div>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="px-4 py-3 flex gap-4" style={{ borderBottom: '1px solid var(--border)' }}>
            {[160, 90, 50, 90].map((w, j) => (
              <div key={j} className={`h-3 ${pulse}`} style={{ ...bg2, width: w }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

/** 8-row list skeleton for Wanted */
export function ListSkeleton() {
  const widths = [200, 160, 180, 140, 170, 155, 190, 145]
  return (
    <div className="space-y-3">
      <div className={`h-7 w-40 ${pulse}`} style={bg2} />
      <div className={`rounded-lg overflow-hidden`} style={bg1}>
        {widths.map((w, i) => (
          <div key={i} className="px-4 py-3 flex items-center gap-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <div className={`h-4 w-4 rounded-full ${pulse}`} style={bg2} />
            <div className={`h-3 ${pulse}`} style={{ ...bg2, width: w }} />
            <div className={`h-3 w-16 ml-auto ${pulse}`} style={bg2} />
          </div>
        ))}
      </div>
    </div>
  )
}

/** Form section skeleton for Settings */
export function FormSkeleton() {
  return (
    <div className="space-y-6">
      <div className={`h-7 w-40 ${pulse}`} style={bg2} />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="space-y-2">
          <div className={`h-3 w-28 ${pulse}`} style={bg2} />
          <div className={`h-9 w-full rounded ${pulse}`} style={bg1} />
        </div>
      ))}
    </div>
  )
}
