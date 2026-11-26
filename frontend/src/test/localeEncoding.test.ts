import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// UTF-8 text read once as Windows-1252 and saved again ("âˆ’" for "−",
// "â€”" for "—", "Ã¼" for "ü"). It showed up in the English scoring settings.
const MOJIBAKE = /\u00e2\u20ac|\u00e2\u02c6|\u00c3[\u0080-\u00bf]|\u00c2[\u00a0-\u00bf]/

const localesDir = join(__dirname, '..', 'i18n', 'locales')

describe('locale files', () => {
  for (const lang of readdirSync(localesDir)) {
    for (const file of readdirSync(join(localesDir, lang))) {
      it(`${lang}/${file} has no double-encoded characters`, () => {
        const lines = readFileSync(join(localesDir, lang, file), 'utf8')
          .split('\n')
          .filter((line) => MOJIBAKE.test(line))
        expect(lines).toEqual([])
      })
    }
  }
})
