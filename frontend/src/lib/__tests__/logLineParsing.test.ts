import { describe, it, expect } from 'vitest'
import {
  CATEGORY_PREFIXES,
  getLineLevel,
  getLevelClassName,
  LEVEL_SEVERITY,
  lineMatchesCategoryPrefixes,
  loggerMatchesPrefixes,
  parseLogLine,
} from '../logLineParsing'

// A realistic text-format line as produced by backend/app_logging.py's
// LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
function textLine(level: string, logger: string, message = 'something happened', reqId = 'req-42') {
  return `2026-09-26 12:00:00,123 [${level}] [${reqId}] ${logger}: ${message}`
}

// A realistic JSON-format line as produced by StructuredJSONFormatter.
function jsonLine(level: string, logger: string, message = 'something happened') {
  return JSON.stringify({
    timestamp: '2026-09-26T12:00:00.123Z',
    level,
    logger,
    message,
    module: logger.split('.').pop(),
    function: 'run',
    line: 1,
  })
}

describe('parseLogLine — text format', () => {
  it('extracts the level from [LEVEL] brackets', () => {
    expect(parseLogLine(textLine('ERROR', 'providers.jimaku')).level).toBe('ERROR')
    expect(parseLogLine(textLine('WARNING', 'providers.jimaku')).level).toBe('WARNING')
    expect(parseLogLine(textLine('INFO', 'providers.jimaku')).level).toBe('INFO')
    expect(parseLogLine(textLine('DEBUG', 'providers.jimaku')).level).toBe('DEBUG')
  })

  it('falls back to INFO when no level bracket is present', () => {
    expect(parseLogLine('a line with no brackets at all').level).toBe('INFO')
  })

  it('extracts the dotted logger name after the request-id bracket', () => {
    expect(parseLogLine(textLine('INFO', 'providers.jimaku')).logger).toBe('providers.jimaku')
    expect(parseLogLine(textLine('INFO', 'translation.llm_base')).logger).toBe('translation.llm_base')
    expect(parseLogLine(textLine('INFO', 'services.wanted_scanner_core')).logger).toBe(
      'services.wanted_scanner_core',
    )
  })

  it('extracts the logger name when the request id is absent ("[-]")', () => {
    const line = textLine('INFO', 'providers.jimaku', 'msg', '-')
    expect(parseLogLine(line).logger).toBe('providers.jimaku')
  })

  it('returns a null logger when the line has no colon-terminated logger segment', () => {
    expect(parseLogLine('2026-09-26 12:00:00,123 [INFO] just some text').logger).toBeNull()
  })
})

describe('parseLogLine — JSON format', () => {
  it('extracts level and logger straight from the JSON keys', () => {
    const parsed = parseLogLine(jsonLine('ERROR', 'providers.jimaku'))
    expect(parsed.level).toBe('ERROR')
    expect(parsed.logger).toBe('providers.jimaku')
  })

  it('uppercases a lowercase level value', () => {
    expect(parseLogLine(jsonLine('warning', 'providers.jimaku')).level).toBe('WARNING')
  })

  it('falls back to INFO for an unrecognized level value', () => {
    expect(parseLogLine(jsonLine('TRACE', 'providers.jimaku')).level).toBe('INFO')
  })

  it('tolerates leading whitespace before the JSON object', () => {
    expect(parseLogLine(`  ${jsonLine('ERROR', 'providers.jimaku')}`).level).toBe('ERROR')
  })

  it('falls back to text parsing for a line that merely starts with "{" but is not valid JSON', () => {
    // Guards against a message that happens to start with "{" (e.g. a repr()
    // dump) being silently misread as a structured line.
    const line = textLine('ERROR', 'providers.jimaku', '{not actually json')
    const parsed = parseLogLine(line)
    expect(parsed.level).toBe('ERROR')
    expect(parsed.logger).toBe('providers.jimaku')
  })
})

describe('getLineLevel / getLevelClassName', () => {
  it('getLineLevel understands both text and JSON lines', () => {
    expect(getLineLevel(textLine('ERROR', 'providers.jimaku'))).toBe('ERROR')
    expect(getLineLevel(jsonLine('ERROR', 'providers.jimaku'))).toBe('ERROR')
  })

  it('maps each level to its Tailwind text-color utility', () => {
    expect(getLevelClassName(textLine('ERROR', 'auth'))).toBe('text-error')
    expect(getLevelClassName(textLine('WARNING', 'auth'))).toBe('text-warning')
    expect(getLevelClassName(textLine('DEBUG', 'auth'))).toBe('text-muted')
    expect(getLevelClassName(textLine('INFO', 'auth'))).toBe('text-foreground')
  })

  // Cold-review fix: CRITICAL lines were falling through to the "unrecognized
  // level" INFO default in both the text-bracket regex and the JSON-level
  // check, so a CRITICAL line was coloured/filtered as if it were the least
  // severe thing in the log — the opposite of the intent.
  it('recognizes CRITICAL (text and JSON) instead of falling back to INFO', () => {
    expect(getLineLevel(textLine('CRITICAL', 'auth'))).toBe('CRITICAL')
    expect(getLineLevel(jsonLine('CRITICAL', 'auth'))).toBe('CRITICAL')
  })

  it('treats CRITICAL like ERROR for colour', () => {
    expect(getLevelClassName(textLine('CRITICAL', 'auth'))).toBe(
      getLevelClassName(textLine('ERROR', 'auth')),
    )
  })

  it('treats CRITICAL like ERROR for severity (so an ERROR-level filter still shows it)', () => {
    expect(LEVEL_SEVERITY.CRITICAL).toBe(LEVEL_SEVERITY.ERROR)
    expect(LEVEL_SEVERITY.CRITICAL).toBeGreaterThan(LEVEL_SEVERITY.WARNING)
  })
})

describe('loggerMatchesPrefixes — module-path segment matching', () => {
  it('matches a provider logger via the "providers" package prefix', () => {
    expect(loggerMatchesPrefixes('providers.jimaku', CATEGORY_PREFIXES.providers)).toBe(true)
    expect(loggerMatchesPrefixes('providers.opensubtitles', CATEGORY_PREFIXES.providers)).toBe(true)
  })

  it('regression guard: the OLD " prefix:" substring check could never fire on a real line', () => {
    // The original bug: CATEGORY_PREFIXES used to list bare provider names
    // ("jimaku") and matched via `line.includes(' jimaku:')`. Logger names
    // are dotted module paths ("providers.jimaku"), so the character right
    // before "jimaku" is "." — never a space — and the old check silently
    // never matched anything. The new segment-based matcher (using the real
    // "providers" package prefix, not a per-provider name) fixes this.
    const line = '2026-09-26 12:00:00,123 [INFO] [req-1] providers.jimaku: found it'
    expect(line.includes(' jimaku:')).toBe(false)
    expect(lineMatchesCategoryPrefixes(line, CATEGORY_PREFIXES.providers)).toBe(true)
  })

  it('matches wanted-scanner modules under the scanner category', () => {
    expect(
      loggerMatchesPrefixes('services.wanted_scanner_core', CATEGORY_PREFIXES.scanner),
    ).toBe(true)
    expect(
      loggerMatchesPrefixes('services.wanted_item_scanner', CATEGORY_PREFIXES.scanner),
    ).toBe(true)
    expect(loggerMatchesPrefixes('standalone.scanner', CATEGORY_PREFIXES.scanner)).toBe(true)
  })

  it('matches translation modules under both translation and translator packages', () => {
    expect(loggerMatchesPrefixes('translation.llm_base', CATEGORY_PREFIXES.translation)).toBe(true)
    expect(loggerMatchesPrefixes('translator._helpers', CATEGORY_PREFIXES.translation)).toBe(true)
  })

  it('matches background-job loggers (apscheduler, worker, services.scheduler)', () => {
    expect(loggerMatchesPrefixes('apscheduler', CATEGORY_PREFIXES.jobs)).toBe(true)
    expect(loggerMatchesPrefixes('worker', CATEGORY_PREFIXES.jobs)).toBe(true)
    expect(loggerMatchesPrefixes('services.scheduler', CATEGORY_PREFIXES.jobs)).toBe(true)
  })

  it('matches both the top-level auth module and routes.auth_ui', () => {
    expect(loggerMatchesPrefixes('auth', CATEGORY_PREFIXES.auth)).toBe(true)
    expect(loggerMatchesPrefixes('routes.auth_ui', CATEGORY_PREFIXES.auth)).toBe(true)
  })

  // Cold-review fix: `backend/ui_auth.py` and `backend/proxy_auth.py` are
  // top-level modules, so their logger names are the bare "ui_auth" /
  // "proxy_auth" — neither equals "auth" nor starts with it (the suffix is
  // "_auth", not a leading "auth"), so they silently fell outside the auth
  // category until listed explicitly.
  it('matches the ui_auth and proxy_auth top-level module loggers', () => {
    expect(loggerMatchesPrefixes('ui_auth', CATEGORY_PREFIXES.auth)).toBe(true)
    expect(loggerMatchesPrefixes('proxy_auth', CATEGORY_PREFIXES.auth)).toBe(true)
  })

  it('does not match an unrelated logger', () => {
    expect(loggerMatchesPrefixes('metadata.tmdb', CATEGORY_PREFIXES.auth)).toBe(false)
  })

  it('returns false for a null logger', () => {
    expect(loggerMatchesPrefixes(null, CATEGORY_PREFIXES.providers)).toBe(false)
  })

  it('has no "api_access" category (werkzeug never fires under gunicorn)', () => {
    expect(CATEGORY_PREFIXES.api_access).toBeUndefined()
  })
})

describe('lineMatchesCategoryPrefixes — end to end on full lines', () => {
  it('matches a provider category line in text format', () => {
    expect(
      lineMatchesCategoryPrefixes(textLine('INFO', 'providers.jimaku'), CATEGORY_PREFIXES.providers),
    ).toBe(true)
  })

  it('matches a provider category line in JSON format', () => {
    expect(
      lineMatchesCategoryPrefixes(jsonLine('INFO', 'providers.jimaku'), CATEGORY_PREFIXES.providers),
    ).toBe(true)
  })

  it('does not match a translation line against the providers category', () => {
    expect(
      lineMatchesCategoryPrefixes(
        textLine('INFO', 'translation.llm_base'),
        CATEGORY_PREFIXES.providers,
      ),
    ).toBe(false)
  })
})
