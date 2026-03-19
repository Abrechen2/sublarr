import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getMediaServerTypes, getMediaServerInstances, saveMediaServerInstances, testMediaServer, getMediaServerHealth,
  getEventCatalog, getHookConfigs, createHookConfig, updateHookConfig, deleteHookConfig, testHook,
  getWebhookConfigs, createWebhookConfig, updateWebhookConfig, deleteWebhookConfig, testWebhook,
  getHookLogs, clearHookLogs,
  getMarketplacePlugins, getMarketplacePlugin, installMarketplacePlugin,
  uninstallMarketplacePlugin, checkMarketplaceUpdates,
  getBazarrMappingReport, runCompatCheck, getExtendedHealthAll,
  exportIntegrationConfig, exportIntegrationConfigZip,
  getAnidbMappingStatus, refreshAnidbMapping,
  getMarketplaceBrowse, refreshMarketplace, getInstalledPlugins,
  installBrowsePlugin, uninstallBrowsePlugin,
  importBazarrConfig, confirmBazarrImport,
} from '@/api/client'
import type { MediaServerInstance, HookConfig, WebhookConfig, BazarrMigrationPreview } from '@/lib/types'
import type { MarketplaceBrowsePlugin } from '@/api/client'

// ─── Media Servers ──────────────────────────────────────────────────────────

export function useMediaServerTypes() {
  return useQuery({
    queryKey: ['mediaServerTypes'],
    queryFn: getMediaServerTypes,
    staleTime: 60_000,
  })
}

export function useMediaServerInstances() {
  return useQuery({
    queryKey: ['mediaServerInstances'],
    queryFn: getMediaServerInstances,
    staleTime: 5 * 60_000,
  })
}

export function useSaveMediaServerInstances() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (instances: MediaServerInstance[]) => saveMediaServerInstances(instances),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mediaServerInstances'] })
    },
  })
}

export function useTestMediaServer() {
  return useMutation({
    mutationFn: (config: Record<string, unknown>) => testMediaServer(config),
  })
}

export function useMediaServerHealth() {
  return useQuery({
    queryKey: ['mediaServerHealth'],
    queryFn: getMediaServerHealth,
    staleTime: 30_000,
  })
}

// ─── Events & Hooks ──────────────────────────────────────────────────────

export function useEventCatalog() {
  return useQuery({ queryKey: ['eventCatalog'], queryFn: getEventCatalog })
}

export function useHookConfigs() {
  return useQuery({ queryKey: ['hookConfigs'], queryFn: () => getHookConfigs() })
}

export function useCreateHook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createHookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookConfigs'] }) },
  })
}

export function useUpdateHook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<HookConfig> }) => updateHookConfig(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookConfigs'] }) },
  })
}

export function useDeleteHook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteHookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookConfigs'] }) },
  })
}

export function useTestHook() {
  return useMutation({ mutationFn: testHook })
}

export function useWebhookConfigs() {
  return useQuery({ queryKey: ['webhookConfigs'], queryFn: () => getWebhookConfigs() })
}

export function useCreateWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createWebhookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['webhookConfigs'] }) },
  })
}

export function useUpdateWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<WebhookConfig> }) => updateWebhookConfig(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['webhookConfigs'] }) },
  })
}

export function useDeleteWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteWebhookConfig,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['webhookConfigs'] }) },
  })
}

export function useTestWebhook() {
  return useMutation({ mutationFn: testWebhook })
}

export function useHookLogs(params?: { hook_id?: number; webhook_id?: number; limit?: number }) {
  return useQuery({ queryKey: ['hookLogs', params], queryFn: () => getHookLogs(params) })
}

export function useClearHookLogs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: clearHookLogs,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['hookLogs'] }) },
  })
}

// ─── Marketplace ────────────────────────────────────────────────────────────────

export function useMarketplacePlugins(category?: string) {
  return useQuery({
    queryKey: ['marketplace', 'plugins', category],
    queryFn: () => getMarketplacePlugins(category),
  })
}

export function useMarketplacePlugin(pluginName: string) {
  return useQuery({
    queryKey: ['marketplace', 'plugin', pluginName],
    queryFn: () => getMarketplacePlugin(pluginName),
    enabled: !!pluginName,
  })
}

export function useInstallMarketplacePlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pluginName, version }: { pluginName: string; version?: string }) =>
      installMarketplacePlugin(pluginName, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace'] })
    },
  })
}

export function useUninstallMarketplacePlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (pluginName: string) => uninstallMarketplacePlugin(pluginName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace'] })
    },
  })
}

export function useCheckMarketplaceUpdates(installedPlugins: string[]) {
  return useQuery({
    queryKey: ['marketplace', 'updates', installedPlugins],
    queryFn: () => checkMarketplaceUpdates(installedPlugins),
    enabled: installedPlugins.length > 0,
  })
}

// ─── External Integrations ──────────────────────────────────────────────────

export function useBazarrMappingReport() {
  return useMutation({
    mutationFn: (dbPath: string) => getBazarrMappingReport(dbPath),
  })
}

export function useCompatCheck() {
  return useMutation({
    mutationFn: ({ subtitlePaths, videoPath, target }: { subtitlePaths: string[]; videoPath: string; target: string }) =>
      runCompatCheck(subtitlePaths, videoPath, target),
  })
}

export function useExtendedHealthAll() {
  return useQuery({
    queryKey: ['extended-health-all'],
    queryFn: getExtendedHealthAll,
    enabled: false,
  })
}

export function useExportIntegrationConfig() {
  return useMutation({
    mutationFn: ({ format, includeSecrets }: { format: string; includeSecrets: boolean }) =>
      exportIntegrationConfig(format, includeSecrets),
  })
}

export function useExportIntegrationConfigZip() {
  return useMutation({
    mutationFn: ({ formats, includeSecrets }: { formats: string[]; includeSecrets: boolean }) =>
      exportIntegrationConfigZip(formats, includeSecrets),
  })
}

// --- Phase 25-02: AniDB ---

export function useAnidbMappingStatus() {
  return useQuery({ queryKey: ['anidb-mapping-status'], queryFn: getAnidbMappingStatus, staleTime: 60000 })
}

export function useRefreshAnidbMapping() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: refreshAnidbMapping,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anidb-mapping-status'] }),
  })
}

// ── v0.22 Marketplace hooks ────────────────────────────────────────────────

export function useMarketplaceBrowse() {
  return useQuery({
    queryKey: ['marketplace', 'browse'],
    queryFn: getMarketplaceBrowse,
    staleTime: 1000 * 60 * 60, // 1h matches backend cache TTL
  })
}

export function useInstalledPlugins() {
  return useQuery({
    queryKey: ['marketplace', 'installed'],
    queryFn: getInstalledPlugins,
  })
}

export function useInstallBrowsePlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (plugin: MarketplaceBrowsePlugin) => installBrowsePlugin(plugin),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'installed'] })
    },
  })
}

export function useUninstallBrowsePlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => uninstallBrowsePlugin(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'installed'] })
    },
  })
}

export function useRefreshMarketplaceBrowse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: refreshMarketplace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'browse'] })
    },
  })
}

// ─── Bazarr Migration ────────────────────────────────────────────────────────

export function useBazarrMigration() {
  return useMutation({
    mutationFn: (file: File) => importBazarrConfig(file),
  })
}

export function useConfirmBazarrImport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (preview: BazarrMigrationPreview) => confirmBazarrImport(preview),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['api-keys'] })
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
  })
}
