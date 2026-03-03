import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diff = (now.getTime() - date.getTime()) / 1000

  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function truncatePath(path: string, maxLen: number = 60): string {
  if (path.length <= maxLen) return path
  const parts = path.split('/')
  if (parts.length <= 3) return '...' + path.slice(-maxLen)
  return parts[0] + '/.../' + parts.slice(-2).join('/')
}

export type MediaTitle = {
  title: string
  episodeCode: string | null
  episodeTitle: string | null
}

const QUALITY_SUFFIX = /\s+(WEBDL|WEB-DL|WEBRip|HDTV|BluRay|Bluray|BDRip|DVDRip|REMUX|Remux|SDR|HDR|\d{3,4}p)[\s\-.].*$/i

export function parseMediaTitle(filePath: string): MediaTitle {
  const filename = filePath.split(/[\\/]/).pop() ?? filePath
  const base = filename.replace(/\.[^.]+$/, '')

  // TV episode: "Show Name - S01E01 - Episode Title Quality-Tags"
  const epMatch = base.match(/^(.+?)\s*[-–]\s*([Ss]\d{2}[Ee]\d{2}(?:-[Ee]\d{2})?)\s*[-–]\s*(.+)$/)
  if (epMatch) {
    const title = epMatch[1].trim()
    const code = epMatch[2].toUpperCase()
    const epTitle = epMatch[3].replace(QUALITY_SUFFIX, '').trim()
    return { title, episodeCode: code, episodeTitle: epTitle || null }
  }

  // Movie: strip [brackets] and quality tags
  const movieTitle = base
    .replace(/\s*[[({][^\])}]+[\])}]/g, '')
    .replace(QUALITY_SUFFIX, '')
    .trim()
  return { title: movieTitle, episodeCode: null, episodeTitle: null }
}
