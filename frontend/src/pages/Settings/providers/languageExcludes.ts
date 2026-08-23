/** Parse the provider_language_excludes_json setting defensively (#192). */
export function parseLanguageExcludes(raw: unknown): Record<string, string[]> {
  if (typeof raw !== 'string' || !raw.trim()) return {}
  try {
    const data: unknown = JSON.parse(raw)
    if (typeof data !== 'object' || data === null || Array.isArray(data)) return {}
    const result: Record<string, string[]> = {}
    for (const [provider, langs] of Object.entries(data)) {
      if (Array.isArray(langs)) {
        const codes = langs.filter((l): l is string => typeof l === 'string' && !!l.trim())
        if (codes.length > 0) result[provider] = codes
      }
    }
    return result
  } catch {
    return {}
  }
}
