/**
 * EventsTab — barrel re-export for backwards compatibility.
 *
 * Contents split into:
 * - EventsHooksTabContent.tsx  (EventsHooksTab export)
 * - ScoringTabContent.tsx      (ScoringTab export)
 *
 * All existing lazy imports from LegacySettings and NotificationsSettings
 * continue to work unchanged via this barrel.
 */
export { EventsHooksTab } from './EventsHooksTabContent'
export { ScoringTab } from './ScoringTabContent'
