/**
 * Path mapping section for the Connections page.
 *
 * The docs have described "Settings → Connections → Path Mapping" with a
 * mapping table and a path test since 1.13.x. The table existed as a finished,
 * fully translated component — and nothing rendered it, so the page it was
 * documented on never showed it (forgejo #25). The first attempt at this fix
 * wired it into InstanceEditor.tsx, which turned out to be dead code itself:
 * the live page builds its instance rows in ConnectionsMediaServers. Checking
 * the rendered UI is what caught that.
 *
 * Bound to the global `path_mapping` setting, which is what
 * POST /settings/path-mapping/test resolves against.
 */
import { FolderTree } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { SettingsSection } from '@/components/settings/SettingsSection'
import { useConfig, useDebouncedConfigSave } from '@/hooks/useApi'
import { strVal } from '@/lib/configUtils'

import { PathMappingEditor } from '../PathMappingEditor'

export function PathMappingSection() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const save = useDebouncedConfigSave()

  return (
    <SettingsSection
      data-testid="path-mapping-section"
      title={t('connections.path_mapping.section_title')}
      description={t('connections.path_mapping.section_desc')}
      icon={<FolderTree size={16} style={{ color: 'var(--accent)' }} />}
    >
      <PathMappingEditor
        value={strVal(config, 'path_mapping', '')}
        onChange={(path_mapping) => save({ path_mapping })}
      />
    </SettingsSection>
  )
}
