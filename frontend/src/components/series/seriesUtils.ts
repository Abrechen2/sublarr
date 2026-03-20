// ─── Language normalisation ─────────────────────────────────────────────────
// MKV/ffprobe stores ISO 639-2 three-letter codes (ger, eng, jpn…). Target
// languages in Sublarr use ISO 639-1 two-letter codes (de, en, ja…).
// normLang() maps 3→2 so that badge de-duplication works across both systems.

export const ISO6392_TO_1: Record<string, string> = {
  ger: 'de', deu: 'de',
  eng: 'en',
  dut: 'nl', nld: 'nl',
  swe: 'sv',
  dan: 'da',
  nor: 'no', nob: 'no', nno: 'no',
  fre: 'fr', fra: 'fr',
  spa: 'es',
  ita: 'it',
  por: 'pt',
  ron: 'ro', rum: 'ro',
  pol: 'pl',
  rus: 'ru',
  ces: 'cs', cze: 'cs',
  slk: 'sk', slo: 'sk',
  hrv: 'hr',
  srp: 'sr',
  bul: 'bg',
  ukr: 'uk',
  jpn: 'ja',
  chi: 'zh', zho: 'zh',
  kor: 'ko',
  tha: 'th',
  vie: 'vi',
  ind: 'id',
  ara: 'ar',
  tur: 'tr',
  hun: 'hu',
  fin: 'fi',
  heb: 'he',
}

export function normLang(code: string): string {
  const lower = code.toLowerCase()
  return ISO6392_TO_1[lower] ?? lower
}

/** Derive subtitle file path from media path + language + format. */
export function deriveSubtitlePath(mediaPath: string, lang: string, format: string): string {
  const lastDot = mediaPath.lastIndexOf('.')
  const base = lastDot > 0 ? mediaPath.substring(0, lastDot) : mediaPath
  return `${base}.${lang}.${format}`
}
