/**
 * What's-New content (V1.6 #5), keyed to backend/VERSION.
 *
 * When the running version (from /health) matches a key here (ignoring any
 * pre-release suffix) and the user hasn't seen it, the WhatsNewModal auto-opens
 * once. Highlight copy lives in i18n under the `common` namespace `whatsnew.*`.
 */
import type { LucideIcon } from 'lucide-react'
import {
  Layers, Columns2, BarChart3, Upload, ShieldCheck, KeyRound,
  Zap, Rocket, Activity, AudioLines, SlidersHorizontal, LogIn, FileDown,
  PauseCircle, Languages, Globe, Gauge, Search,
} from 'lucide-react'

export interface WhatsNewItem {
  icon: LucideIcon
  titleKey: string
  descKey: string
}

export const WHATS_NEW: Record<string, WhatsNewItem[]> = {
  '1.12.2': [
    { icon: Languages, titleKey: 'whatsnew.v1122.translation_retry_title', descKey: 'whatsnew.v1122.translation_retry_desc' },
    { icon: Activity, titleKey: 'whatsnew.v1122.file_missing_title', descKey: 'whatsnew.v1122.file_missing_desc' },
    { icon: Gauge, titleKey: 'whatsnew.v1122.opensubtitles_test_title', descKey: 'whatsnew.v1122.opensubtitles_test_desc' },
  ],
  '1.12.1': [
    { icon: Languages, titleKey: 'whatsnew.v1121.search_translate_title', descKey: 'whatsnew.v1121.search_translate_desc' },
    { icon: Activity, titleKey: 'whatsnew.v1121.queue_orphan_title', descKey: 'whatsnew.v1121.queue_orphan_desc' },
    { icon: PauseCircle, titleKey: 'whatsnew.v1121.cancel_title', descKey: 'whatsnew.v1121.cancel_desc' },
    { icon: Gauge, titleKey: 'whatsnew.v1121.grace_title', descKey: 'whatsnew.v1121.grace_desc' },
    { icon: Zap, titleKey: 'whatsnew.v1121.webhook_title', descKey: 'whatsnew.v1121.webhook_desc' },
  ],
  '1.12.0': [
    { icon: Search, titleKey: 'whatsnew.v1120.sidecar_queue_title', descKey: 'whatsnew.v1120.sidecar_queue_desc' },
    { icon: PauseCircle, titleKey: 'whatsnew.v1120.startup_search_title', descKey: 'whatsnew.v1120.startup_search_desc' },
    { icon: Activity, titleKey: 'whatsnew.v1120.automation_timeout_title', descKey: 'whatsnew.v1120.automation_timeout_desc' },
  ],
  '1.11.2': [
    { icon: Search, titleKey: 'whatsnew.v1112.search_stall_title', descKey: 'whatsnew.v1112.search_stall_desc' },
    { icon: FileDown, titleKey: 'whatsnew.v1112.logs_title', descKey: 'whatsnew.v1112.logs_desc' },
    { icon: Activity, titleKey: 'whatsnew.v1112.next_run_title', descKey: 'whatsnew.v1112.next_run_desc' },
  ],
  '1.11.1': [
    { icon: Activity, titleKey: 'whatsnew.v1111.provider_test_title', descKey: 'whatsnew.v1111.provider_test_desc' },
  ],
  '1.11.0': [
    { icon: Languages, titleKey: 'whatsnew.v1110.sweep_title', descKey: 'whatsnew.v1110.sweep_desc' },
    { icon: Globe, titleKey: 'whatsnew.v1110.deepl_title', descKey: 'whatsnew.v1110.deepl_desc' },
    { icon: Gauge, titleKey: 'whatsnew.v1110.limits_title', descKey: 'whatsnew.v1110.limits_desc' },
    { icon: Search, titleKey: 'whatsnew.v1110.upgrade_title', descKey: 'whatsnew.v1110.upgrade_desc' },
  ],
  '1.10.0': [
    { icon: AudioLines, titleKey: 'whatsnew.v1100.waveform_title', descKey: 'whatsnew.v1100.waveform_desc' },
    { icon: Activity, titleKey: 'whatsnew.v1100.decision_title', descKey: 'whatsnew.v1100.decision_desc' },
    { icon: SlidersHorizontal, titleKey: 'whatsnew.v1100.scoring_title', descKey: 'whatsnew.v1100.scoring_desc' },
    { icon: LogIn, titleKey: 'whatsnew.v1100.login_title', descKey: 'whatsnew.v1100.login_desc' },
    { icon: FileDown, titleKey: 'whatsnew.v1100.export_title', descKey: 'whatsnew.v1100.export_desc' },
    { icon: PauseCircle, titleKey: 'whatsnew.v1100.pause_title', descKey: 'whatsnew.v1100.pause_desc' },
  ],
  '1.9.4': [
    { icon: Zap, titleKey: 'whatsnew.v194.speed_title', descKey: 'whatsnew.v194.speed_desc' },
    { icon: Rocket, titleKey: 'whatsnew.v194.load_title', descKey: 'whatsnew.v194.load_desc' },
    { icon: Activity, titleKey: 'whatsnew.v194.load2_title', descKey: 'whatsnew.v194.load2_desc' },
    { icon: BarChart3, titleKey: 'whatsnew.v194.stats_title', descKey: 'whatsnew.v194.stats_desc' },
  ],
  '1.6.0': [
    { icon: Layers, titleKey: 'whatsnew.v160.combined_title', descKey: 'whatsnew.v160.combined_desc' },
    { icon: Columns2, titleKey: 'whatsnew.v160.sync_compare_title', descKey: 'whatsnew.v160.sync_compare_desc' },
    { icon: BarChart3, titleKey: 'whatsnew.v160.statistics_title', descKey: 'whatsnew.v160.statistics_desc' },
    { icon: Upload, titleKey: 'whatsnew.v160.upload_title', descKey: 'whatsnew.v160.upload_desc' },
    { icon: ShieldCheck, titleKey: 'whatsnew.v160.proxy_auth_title', descKey: 'whatsnew.v160.proxy_auth_desc' },
    { icon: KeyRound, titleKey: 'whatsnew.v160.encryption_title', descKey: 'whatsnew.v160.encryption_desc' },
  ],
}

/** Normalise a running version ("1.6.0-beta") to a content key ("1.6.0"). */
export function versionKey(version: string | undefined): string | null {
  if (!version) return null
  const base = version.trim().replace(/^v/, '').split(/[-+]/)[0]
  return base in WHATS_NEW ? base : null
}
