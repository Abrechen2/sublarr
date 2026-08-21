import { useTranslation } from 'react-i18next'
import { SettingRow } from '@/components/shared/SettingRow'
import { LanguagePillSelector } from '@/components/settings/LanguagePillSelector'
import { useConfig, useSupportedLanguages, useUpdateConfig } from '@/hooks/useApi'
import { parseLanguageExcludes } from './languageExcludes'

interface Props {
  readonly providerName: string
  /** ISO 639-1 codes the provider declares support for (from /providers). */
  readonly providerLanguages?: readonly string[]
}

/**
 * Per-provider language exclusion (#192) — languages this provider must
 * never search or serve. Stored in the `provider_language_excludes_json`
 * config setting as `{ providerName: ["sr", ...] }`.
 */
export function ProviderLanguageExcludes({ providerName, providerLanguages }: Props) {
  const { t: ts } = useTranslation('settings')
  const { data: config } = useConfig()
  const { data: supportedLanguages = [] } = useSupportedLanguages()
  const updateConfig = useUpdateConfig()

  const excludes = parseLanguageExcludes(config?.provider_language_excludes_json)
  const value = excludes[providerName] ?? []

  // Offer only languages the provider actually supports; fall back to the
  // global list for providers that don't declare a language set.
  const nameByCode = new Map(supportedLanguages.map((l) => [l.code, l.name]))
  const codes =
    providerLanguages && providerLanguages.length > 0
      ? providerLanguages
      : supportedLanguages.map((l) => l.code)
  const options = codes.map((code) => ({
    value: code,
    label: nameByCode.get(code) ? `${nameByCode.get(code)} (${code})` : code,
  }))

  const handleChange = (newValue: string[]) => {
    const next: Record<string, string[]> = { ...excludes, [providerName]: newValue }
    if (newValue.length === 0) {
      delete next[providerName]
    }
    updateConfig.mutate({
      provider_language_excludes_json: Object.keys(next).length > 0 ? JSON.stringify(next) : '',
    })
  }

  return (
    <SettingRow
      label={ts('providers_tab.editor.excluded_languages')}
      description={ts('providers_tab.editor.excluded_languages_hint')}
    >
      <div className="w-full" data-testid={`provider-language-excludes-${providerName}`}>
        <LanguagePillSelector
          value={value}
          options={options}
          onChange={handleChange}
          placeholder={ts('providers_tab.editor.excluded_languages_placeholder')}
        />
      </div>
    </SettingRow>
  )
}
