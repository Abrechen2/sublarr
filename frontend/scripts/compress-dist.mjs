// Post-build: pre-compress text assets in dist/ to .br (brotli) and .gz (gzip)
// siblings, so the backend can serve them with Content-Encoding without any
// per-request CPU. Vite ships JS/CSS uncompressed; on low-power hosts (NAS/Pi)
// that made first-load of each lazy route chunk slow. Dependency-free — uses
// Node's built-in zlib (brotli since Node 11.7).
import { readdirSync, statSync, readFileSync, writeFileSync } from 'node:fs'
import { join, extname, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { brotliCompressSync, gzipSync, constants } from 'node:zlib'

const DIST = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const COMPRESSIBLE = new Set(['.js', '.css', '.html', '.svg', '.json', '.map'])
const MIN_BYTES = 1024 // below this, compression headers cost more than they save

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else yield p
  }
}

let count = 0
let rawTotal = 0
let brTotal = 0
for (const file of walk(DIST)) {
  if (file.endsWith('.br') || file.endsWith('.gz')) continue
  if (!COMPRESSIBLE.has(extname(file))) continue
  const buf = readFileSync(file)
  if (buf.length < MIN_BYTES) continue
  const br = brotliCompressSync(buf, {
    params: {
      [constants.BROTLI_PARAM_QUALITY]: 11,
      [constants.BROTLI_PARAM_SIZE_HINT]: buf.length,
    },
  })
  writeFileSync(file + '.br', br)
  writeFileSync(file + '.gz', gzipSync(buf, { level: 9 }))
  count++
  rawTotal += buf.length
  brTotal += br.length
}

const pct = rawTotal ? Math.round((1 - brTotal / rawTotal) * 100) : 0
console.log(
  `compress-dist: ${count} assets pre-compressed (br+gz), ` +
    `${(rawTotal / 1024 / 1024).toFixed(1)} MB -> ${(brTotal / 1024 / 1024).toFixed(1)} MB brotli (-${pct}%)`,
)
