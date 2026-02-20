/** Shared disk space utilities used by both DiskSpaceWidget variants. */

export const FORMAT_COLORS: Record<string, string> = {
  ass: '#14b8a6',  // teal
  srt: '#f59e0b',  // amber
  ssa: '#8b5cf6',  // violet
  sub: '#6366f1',  // indigo
  vtt: '#ec4899',  // pink
}

export function getFormatColor(format: string): string {
  return FORMAT_COLORS[format.toLowerCase()] ?? '#94a3b8'  // slate fallback
}

/** Format bytes into human-readable KB/MB/GB */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}
