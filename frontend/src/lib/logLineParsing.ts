/**
 * Parsing helpers for a single log line, shared by the live Logs viewer
 * (`pages/Logs.tsx`) and its category/level filters.
 *
 * Two log line shapes exist side by side, selected by `SUBLARR_LOG_FORMAT`:
 *  - text:  "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
 *           e.g. `2026-09-26 12:00:00,123 [INFO] [req-42] providers.jimaku: found it`
 *  - json:  one JSON object per line with "level" and "logger" keys
 *           (see backend/app_logging.py StructuredJSONFormatter).
 *
 * `%(name)s` / the JSON "logger" field is the Python logger name, i.e. a
 * dotted MODULE PATH such as "providers.jimaku" or "translation.llm_base" —
 * not a bare provider/category name. Matching must therefore compare against
 * path segments, not a literal substring like " jimaku:".
 */

export const KNOWN_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
export type KnownLogLevel = (typeof KNOWN_LOG_LEVELS)[number]

export interface ParsedLogLine {
  level: KnownLogLevel
  /** Dotted logger name (e.g. "providers.jimaku"), or null if it could not be found. */
  logger: string | null
}

function isKnownLevel(value: string): value is KnownLogLevel {
  return (KNOWN_LOG_LEVELS as readonly string[]).includes(value)
}

function parseJsonLogLine(trimmed: string): ParsedLogLine | null {
  if (!trimmed.startsWith('{')) return null
  try {
    const obj = JSON.parse(trimmed) as Record<string, unknown>
    const rawLevel = typeof obj.level === 'string' ? obj.level.toUpperCase() : ''
    const level = isKnownLevel(rawLevel) ? rawLevel : 'INFO'
    const logger = typeof obj.logger === 'string' ? obj.logger : null
    return { level, logger }
  } catch {
    return null
  }
}

/** Parses either log-line shape into a level + logger name. Never throws. */
export function parseLogLine(line: string): ParsedLogLine {
  const json = parseJsonLogLine(line.trim())
  if (json) return json

  const levelMatch = line.match(/\[(DEBUG|INFO|WARNING|ERROR)\]/)
  // The text format has two "] " brackets before the logger name (level,
  // then request id) — matching on the LAST one avoids picking up "[INFO]"
  // itself. `.match()` without /g/ still finds this because the engine
  // retries at every start index, and "[req-42]" doesn't start with an
  // identifier character so it is skipped automatically.
  const loggerMatch = line.match(/\]\s+([A-Za-z_][\w.-]*):/)

  return {
    level: levelMatch ? (levelMatch[1] as KnownLogLevel) : 'INFO',
    logger: loggerMatch ? loggerMatch[1] : null,
  }
}

export function getLineLevel(line: string): KnownLogLevel {
  return parseLogLine(line).level
}

/**
 * True if a dotted logger name belongs to one of the given category prefixes.
 * A prefix matches when it equals the full logger name, is a leading dotted
 * segment of it (`services.wanted_scanner` matches `services.wanted_scanner.core`),
 * or matches/starts one of the logger's own dot-separated segments
 * (`jimaku` is not used any more, but `wanted_scanner` matches the segment
 * `wanted_scanner_core` in `services.wanted_scanner_core`).
 */
export function loggerMatchesPrefixes(logger: string | null, prefixes: string[]): boolean {
  if (!logger) return false
  const segments = logger.split('.')
  return prefixes.some(
    (prefix) =>
      logger === prefix ||
      logger.startsWith(`${prefix}.`) ||
      segments.some((seg) => seg === prefix || seg.startsWith(prefix)),
  )
}

/** Convenience: parses `line` and checks its logger against `prefixes`. */
export function lineMatchesCategoryPrefixes(line: string, prefixes: string[]): boolean {
  return loggerMatchesPrefixes(parseLogLine(line).logger, prefixes)
}

/**
 * Category → logger-prefix map for the Logs page's category filters.
 *
 * `api_access` (werkzeug access logs) was removed: under Gunicorn (the only
 * way Sublarr ships) access logging goes through gunicorn's own "gunicorn.access"
 * logger straight to stdout/Docker logs, never through the app's own handlers —
 * so werkzeug's access log line never reaches the file the Logs page reads and
 * the category could never fire.
 */
export const CATEGORY_PREFIXES: Record<string, string[]> = {
  scanner: ['wanted_scanner', 'wanted_item_scanner', 'standalone'],
  translation: ['translation', 'translator'],
  providers: ['providers'],
  jobs: ['apscheduler', 'worker', 'services.scheduler'],
  auth: ['auth'],
}

const LEVEL_CLASS: Record<KnownLogLevel, string> = {
  ERROR: 'text-error',
  WARNING: 'text-warning',
  DEBUG: 'text-muted',
  INFO: 'text-foreground',
}

/** Tailwind text-color utility class for a line's level. */
export function getLevelClassName(line: string): string {
  return LEVEL_CLASS[getLineLevel(line)]
}
