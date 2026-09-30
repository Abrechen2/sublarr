import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Every URL the app builds has to carry the reverse-proxy prefix.
 *
 * rc.19, checked live under /sublarr: the shared axios client did, but the
 * auth bootstrap, five hand-built download/stream/preview URLs, the webhook
 * URLs shown for Sonarr/Radarr/Jellyfin and the Socket.IO connection all went
 * to "/". Sublarr still answers there, so it looked fine — behind a proxy
 * that only forwards the prefix, login and those features fail.
 */
const SRC = join(__dirname, '..')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return name === '__tests__' ? [] : sourceFiles(path)
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
  })
}

// A string or template literal that STARTS with an app-absolute API or socket
// path. Comments and doc strings that merely mention a path do not match,
// because they are not quoted at the start of a literal.
const ABSOLUTE = /(['"`])\/(api\/v1|socket\.io)\b/

describe('base path coverage', () => {
  it('no source builds an app-absolute URL without withBase()', () => {
    const offenders = sourceFiles(SRC).flatMap((file) =>
      readFileSync(file, 'utf-8')
        .split('\n')
        .map((line, i) => ({ line: line.trim(), where: `${file.slice(SRC.length + 1)}:${i + 1}` }))
        .filter(({ line }) => !line.startsWith('*') && !line.startsWith('//'))
        .filter(({ line }) => ABSOLUTE.test(line) && !line.includes('withBase('))
        .map(({ where, line }) => `${where}  ${line}`),
    )
    expect(offenders).toEqual([])
  })

  it('the socket connects under the prefix', () => {
    const source = readFileSync(join(SRC, 'contexts', 'WebSocketContext.tsx'), 'utf-8')
    expect(source).toMatch(/path:\s*withBase\('\/socket\.io'\)/)
  })
})
