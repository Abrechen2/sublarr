import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// GitHub #148: an unlayered `*{margin:0;padding:0}` reset in index.css outranked
// Tailwind's @layer utilities and silently stripped every spacing utility
// (p-*, m-*, gap-*) app-wide; the same report's console errors came from
// websocket upgrades the threading server cannot answer.
const SRC = resolve(import.meta.dirname, '..')

/** Top-level (unlayered) rules of a stylesheet as [selector, body] pairs. */
function topLevelRules(css: string): [string, string][] {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const rules: [string, string][] = []
  let depth = 0
  let start = 0
  let selector = ''
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{') {
      if (depth === 0) {
        selector = text.slice(start, i).trim()
        start = i + 1
      }
      depth++
    } else if (text[i] === '}') {
      depth--
      if (depth === 0) {
        rules.push([selector, text.slice(start, i)])
        start = i + 1
      }
    } else if (text[i] === ';' && depth === 0) {
      start = i + 1
    }
  }
  return rules
}

describe('global styles (GitHub #148)', () => {
  it('no unlayered universal rule resets margin or padding', () => {
    const css = readFileSync(join(SRC, 'index.css'), 'utf-8')
    const offending = topLevelRules(css).filter(
      ([selector, body]) =>
        !selector.startsWith('@') &&
        selector.split(',').some((s) => s.trim().startsWith('*')) &&
        /(^|[;\s])(margin|padding)\s*:/.test(body),
    )
    expect(offending.map(([selector]) => selector)).toEqual([])
  })

  it('the parser sees such a reset (positive control)', () => {
    const rules = topLevelRules('@layer base { * { margin: 0 } }\n* { margin: 0; padding: 0 }')
    expect(rules.filter(([s]) => s === '*')).toHaveLength(1)
  })

  it('the socket client uses polling only', () => {
    const ctx = readFileSync(join(SRC, 'contexts/WebSocketContext.tsx'), 'utf-8')
    expect(ctx).toMatch(/transports:\s*\[\s*'polling'\s*\]/)
  })
})
