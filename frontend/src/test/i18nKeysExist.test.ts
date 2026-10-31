import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

// Audit #61 A33/A37: chart legends, the comparison view and an export toast
// showed raw keys because the keys did not exist, a section used the wrong
// namespace, and whole catalog branches were never read. A key written in code
// without an inline default must exist in en AND de; the two catalogs must
// hold the same keys.

const SRC = resolve(import.meta.dirname, '..')
const LOCALES = join(SRC, 'i18n/locales')
type Tree = { [k: string]: Tree | string }

function load(lang: string): Record<string, Tree> {
  const out: Record<string, Tree> = {}
  for (const f of readdirSync(join(LOCALES, lang))) {
    if (f.endsWith('.json')) out[f.slice(0, -5)] = JSON.parse(readFileSync(join(LOCALES, lang, f), 'utf-8'))
  }
  return out
}

function flatten(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === 'string' ? [prefix + k] : flatten(v, `${prefix}${k}.`),
  )
}

function has(cat: Record<string, Tree>, ns: string, key: string): boolean {
  let node: Tree | string | undefined = cat[ns]
  for (const part of key.split('.')) {
    if (!node || typeof node === 'string') return false
    node = node[part]
  }
  if (node !== undefined) return true
  return ['_one', '_other'].some((suffix) => has(cat, ns, key + suffix))
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return name === '__tests__' || name === 'i18n' ? [] : sourceFiles(full)
    return /\.(ts|tsx)$/.test(name) && !/\.test\./.test(name) ? [full] : []
  })
}

const en = load('en')
const de = load('de')

describe('i18n catalogs', () => {
  it('en and de hold the same keys', () => {
    for (const ns of Object.keys(en)) {
      expect(flatten(de[ns] ?? {}).sort(), ns).toEqual(flatten(en[ns]).sort())
    }
  })

  it('every key used without an inline default exists in en and de', () => {
    const missing: string[] = []
    const useRe = /const\s*\{\s*t(?:\s*:\s*(\w+))?\s*\}\s*=\s*useTranslation\(\s*(?:'([\w-]+)'|\[\s*'([\w-]+)')?/g
    for (const file of sourceFiles(SRC)) {
      const src = readFileSync(file, 'utf-8')
      const aliases = new Map<string, Set<string>>()
      for (const m of src.matchAll(useRe)) {
        const alias = m[1] ?? 't'
        if (!aliases.has(alias)) aliases.set(alias, new Set())
        aliases.get(alias)!.add(m[2] ?? m[3] ?? 'common')
      }
      for (const [alias, namespaces] of aliases) {
        const callRe = new RegExp(`(?<![\\w.])${alias}\\(\\s*'([\\w.:-]+)'\\s*(,\\s*(['"\`{]))?`, 'g')
        for (const m of src.matchAll(callRe)) {
          if (m[3] && m[3] !== '{') continue // inline default text
          const lineStart = src.lastIndexOf('\n', m.index!) + 1
          if (/^\s*(\*|\/\/|\/\*)/.test(src.slice(lineStart, m.index!))) continue // comment
          let key = m[1]
          let candidates = [...namespaces]
          // The options object of THIS call, cut before a nested t(…) call.
          const args = src.slice(m.index! + m[0].length, m.index! + 160).split(/\bt\w*\(/)[0]
          const nsOption = m[3] === '{' ? /\bns:\s*'([\w-]+)'/.exec(args) : null
          if (nsOption) candidates = [nsOption[1]]
          if (key.includes(':')) {
            const [ns, rest] = key.split(':', 2)
            candidates = [ns]
            key = rest
          }
          for (const [lang, cat] of [['en', en], ['de', de]] as const) {
            if (!candidates.some((ns) => has(cat, ns, key))) {
              const line = src.slice(0, m.index).split('\n').length
              missing.push(`${relative(SRC, file)}:${line} ${candidates.join('|')}:${key} (${lang})`)
            }
          }
        }
      }
    }
    expect(missing).toEqual([])
  })
})
