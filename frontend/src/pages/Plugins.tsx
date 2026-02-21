/**
 * Plugins Page - Community plugin marketplace.
 *
 * Browse, install, and manage community-provided plugins.
 */

import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Download, Trash2, ExternalLink, Loader2, Package, Star } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useMarketplacePlugins,
  useInstallMarketplacePlugin,
  useUninstallMarketplacePlugin,
} from '@/hooks/useApi'

interface Plugin {
  name: string
  version: string
  description: string
  author: string
  category: 'provider' | 'translation' | 'tool'
  url: string
  rating?: number
  downloads?: number
}

export function PluginsPage() {
  const { t } = useTranslation('plugins')
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<'all' | 'provider' | 'translation' | 'tool'>('all')
  const [installedPlugins, setInstalledPlugins] = useState<string[]>([])

  const categoryParam = categoryFilter === 'all' ? undefined : categoryFilter
  const { data: pluginsData, isLoading } = useMarketplacePlugins(categoryParam)
  const installMutation = useInstallMarketplacePlugin()
  const uninstallMutation = useUninstallMarketplacePlugin()

  const plugins = pluginsData?.plugins || []

  const filteredPlugins = plugins.filter((plugin) => {
    const matchesSearch = plugin.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      plugin.description.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = categoryFilter === 'all' || plugin.category === categoryFilter
    return matchesSearch && matchesCategory
  })

  const handleInstall = useCallback(async (pluginName: string) => {
    try {
      await installMutation.mutateAsync({ pluginName })
      setInstalledPlugins((prev) => [...prev, pluginName])
      toast(`Plugin "${pluginName}" installed successfully`, 'success')
    } catch (err) {
      toast(`Failed to install plugin "${pluginName}"`, 'error')
    }
  }, [installMutation])

  const handleUninstall = useCallback(async (pluginName: string) => {
    try {
      await uninstallMutation.mutateAsync(pluginName)
      setInstalledPlugins((prev) => prev.filter((name) => name !== pluginName))
      toast(`Plugin "${pluginName}" uninstalled`, 'success')
    } catch (err) {
      toast(`Failed to uninstall plugin "${pluginName}"`, 'error')
    }
  }, [uninstallMutation])

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold mb-2">Plugin Marketplace</h1>
        <p className="text-gray-400">
          Browse and install community-provided plugins to extend Sublarr's functionality.
        </p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search plugins..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-500"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as typeof categoryFilter)}
          className="px-4 py-2 bg-gray-900 border border-gray-700 rounded text-white"
        >
          <option value="all">All Categories</option>
          <option value="provider">Providers</option>
          <option value="translation">Translation</option>
          <option value="tool">Tools</option>
        </select>
      </div>

      {/* Plugin List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-teal-500" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredPlugins.map((plugin) => {
            const isInstalled = installedPlugins.includes(plugin.name)
            const isInstallingThis = installMutation.isPending && installMutation.variables?.pluginName === plugin.name

          return (
            <div
              key={plugin.name}
              className="bg-gray-900 rounded-lg p-6 border border-gray-700 hover:border-teal-500 transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Package className="w-5 h-5 text-teal-500" />
                    {plugin.name}
                  </h3>
                  <p className="text-sm text-gray-400 mt-1">{plugin.version}</p>
                </div>
                {plugin.rating && (
                  <div className="flex items-center gap-1 text-yellow-400">
                    <Star className="w-4 h-4 fill-current" />
                    <span className="text-sm">{plugin.rating}</span>
                  </div>
                )}
              </div>

              <p className="text-gray-300 mb-4 text-sm">{plugin.description}</p>

              <div className="flex items-center justify-between text-xs text-gray-400 mb-4">
                <span>By {plugin.author}</span>
                {plugin.downloads && <span>{plugin.downloads} downloads</span>}
              </div>

              <div className="flex gap-2">
                {isInstalled ? (
                  <button
                    onClick={() => handleUninstall(plugin.name)}
                    className="flex-1 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded flex items-center justify-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" />
                    Uninstall
                  </button>
                ) : (
                  <button
                    onClick={() => handleInstall(plugin.name)}
                    disabled={isInstallingThis}
                    className="flex-1 px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isInstallingThis ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Download className="w-4 h-4" />
                    )}
                    Install
                  </button>
                )}
                <button
                  onClick={() => window.open(plugin.url, '_blank')}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded"
                  title="View on GitHub"
                >
                  <ExternalLink className="w-4 h-4" />
                </button>
              </div>
            </div>
          )
        })}
        </div>
      )}

      {!isLoading && filteredPlugins.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <Package className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No plugins found matching your criteria.</p>
        </div>
      )}
    </div>
  )
}
