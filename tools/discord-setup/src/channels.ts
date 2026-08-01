/**
 * Channel names, discovered from the live guild on 2026-08-01 with
 * `npm run read` (31 channels) and chosen by the owner.
 *
 * Names, not ids: every lookup in this tool is name-addressed, and a renamed
 * channel should fail loudly ("target channel not found") rather than keep
 * posting somewhere the name no longer describes.
 */

export const ANNOUNCE_CHANNELS = {
  beta: "beta-channel",
  /**
   * Sublarr has no dedicated release-candidate channel, so RC announcements
   * share the beta channel — that is where the testers already are. This is a
   * deliberate choice, not a missing constant: do not invent a #release-candidate.
   */
  rc: "beta-channel",
  release: "announcements",
} as const;

/**
 * Where announcements ask people to report back. Lives in the #BETA category,
 * which is role-restricted — the bot needs that category granted, or the
 * announcement will point at a channel its own readers may not see.
 */
export const FEEDBACK_CHANNEL = "beta-feedback";
