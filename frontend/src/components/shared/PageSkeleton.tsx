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
