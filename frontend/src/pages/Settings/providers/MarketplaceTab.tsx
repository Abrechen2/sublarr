import { useState, useCallback } from 'react'
import {
  Search, RefreshCw, Download, Trash2, ExternalLink,
  Loader2, Package, ShieldCheck,
} from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useMarketplaceBrowse,
  useInstalledPlugins,
  useInstallBrowsePlugin,
  useUninstallBrowsePlugin,
  useRefreshMarketplaceBrowse,
} from '@/hooks/useApi'
import { CapabilityWarningModal } from './CapabilityWarningModal'
import type { MarketplaceBrowsePlugin } from '@/api/client'

const HIGH_RISK = new Set(['filesystem', 'subprocess'])

function hasRiskyCapabilities(capabilities: string[]): boolean {
  return capabilities.some((c) => HIGH_RISK.has(c))
}

export function MarketplaceTab() {
  const [search, setSearch] = useState('')
  const [onlyInstalled, setOnlyInstalled] = useState(false)
  const [pendingInstall, setPendingInstall] = useState<MarketplaceBrowsePlugin | null>(null)

  const { data: browseData, isLoading } = useMarketplaceBrowse()
  const { data: installedData } = useInstalledPlugins()
  const installMutation = useInstallBrowsePlugin()
  const uninstallMutation = useUninstallBrowsePlugin()
  const refreshMutation = useRefreshMarketplaceBrowse()

  const installedNames = new Set(installedData?.installed.map((p) => p.name) ?? [])
  const installedVersions = Object.fromEntries(
    installedData?.installed.map((p) => [p.name, p.version]) ?? []
  )
  const allPlugins = browseData?.plugins ?? []

  const filtered = allPlugins.filter((p) => {
    const matchSearch =
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.display_name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase())
    const matchInstalled = !onlyInstalled || installedNames.has(p.name)
    return matchSearch && matchInstalled
  })

  const doInstall = useCallback(async (plugin: MarketplaceBrowsePlugin) => {
    setPendingInstall(null)
    try {
      await installMutation.mutateAsync(plugin)
      toast(`"${plugin.display_name}" installed`, 'success')
    } catch {
      toast(`Failed to install "${plugin.display_name}"`, 'error')
    }
  }, [installMutation])

  const handleInstallRequest = useCallback((plugin: MarketplaceBrowsePlugin) => {
    if (!plugin.is_official && hasRiskyCapabilities(plugin.capabilities)) {
      setPendingInstall(plugin)
    } else {
      void doInstall(plugin)
    }
  }, [doInstall])

  const handleUninstall = useCallback(async (name: string, displayName: string) => {
    try {
      await uninstallMutation.mutateAsync(name)
      toast(`"${displayName}" removed`, 'success')
    } catch {
      toast(`Failed to remove "${displayName}"`, 'error')
    }
  }, [uninstallMutation])

  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search plugins..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlyInstalled}
            onChange={(e) => setOnlyInstalled(e.target.checked)}
            className="rounded"
          />
          Installed only
        </label>
        <button
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded flex items-center gap-2 text-sm disabled:opacity-50"
          title="Refresh from GitHub"
        >
          <RefreshCw className={`w-4 h-4 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-teal-500" />
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((plugin) => {
            const installed = installedNames.has(plugin.name)
            const currentVersion = installedVersions[plugin.name]
            const hasUpdate = installed && currentVersion !== undefined && currentVersion !== plugin.version
            const isInstalling =
              installMutation.isPending &&
              (installMutation.variables as MarketplaceBrowsePlugin | undefined)?.name === plugin.name

            return (
              <div
                key={plugin.name}
                className="flex items-start gap-4 p-4 bg-gray-800 rounded-lg border border-gray-700"
              >
                <Package className="w-5 h-5 text-teal-500 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-white">{plugin.display_name}</span>
                    <span className="text-xs text-gray-400">v{plugin.version}</span>
                    {plugin.is_official ? (
                      <span className="flex items-center gap-1 text-xs bg-green-600/20 text-green-400 px-2 py-0.5 rounded-full">
                        <ShieldCheck className="w-3 h-3" /> Official
                      </span>
                    ) : (
                      <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded-full">
                        Community
                      </span>
                    )}
                    {hasUpdate && (
                      <span className="text-xs bg-yellow-600/20 text-yellow-400 px-2 py-0.5 rounded-full">
                        Update → v{plugin.version}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-400 mt-1 truncate">{plugin.description}</p>
                  <p className="text-xs text-gray-500 mt-0.5">by {plugin.author}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <a
                    href={plugin.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1.5 text-gray-400 hover:text-white rounded"
                    title="View on GitHub"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                  {installed ? (
                    <button
                      onClick={() => void handleUninstall(plugin.name, plugin.display_name)}
                      className="px-3 py-1.5 text-sm bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded flex items-center gap-1.5"
                    >
                      <Trash2 className="w-4 h-4" />
                      Remove
                    </button>
                  ) : (
                    <button
                      onClick={() => handleInstallRequest(plugin)}
                      disabled={isInstalling}
                      className="px-3 py-1.5 text-sm bg-teal-600 hover:bg-teal-500 text-white rounded flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {isInstalling ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      Install
                    </button>
                  )}
                </div>
              </div>
            )
          })}
          {filtered.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <Package className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>No plugins found.</p>
            </div>
          )}
        </div>
      )}

      {pendingInstall !== null && (
        <CapabilityWarningModal
          plugin={pendingInstall}
          onConfirm={() => void doInstall(pendingInstall)}
          onCancel={() => setPendingInstall(null)}
        />
      )}
    </div>
  )
}
