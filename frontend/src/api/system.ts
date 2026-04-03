/**
 * api/system.ts — barrel re-export for backwards compatibility.
 *
 * Contents split into domain modules under api/system/:
 * - history.ts       — blacklist + download history
 * - logs.ts          — logs, log rotation, support export, notification test/status
 * - standalone.ts    — standalone mode, statistics, full backup
 * - tasks.ts         — scheduler tasks, health check, sync, auto-sync, cleanup, video sync
 * - notifications.ts — notification templates, quiet hours, history, filters
 * - tools.ts         — subtitle tools, audio, spell, OCR, integrations, quality fixes,
 *                      format conversion, waveform, subtitle diff, subtitle processing
 *
 * All existing imports from '@/api/system' continue to work unchanged.
 */
export * from './system/history'
export * from './system/logs'
export * from './system/standalone'
export * from './system/tasks'
export * from './system/notifications'
export * from './system/tools'
