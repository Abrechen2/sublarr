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
   * `#release-candidate` was created 2026-08-01 in the same `BETA` category as
   * `#beta-channel`, so RC announcements now have their own lane while still
   * reaching the same testers (the category's permissions carry over).
   */
  rc: "release-candidate",
  release: "announcements",
} as const;

/**
 * `#changelog` is deliberately NOT an announce lane. A GitHub Actions
 * workflow used to mirror every release and pre-release there; it was
 * retired 2026-08-01 and nothing writes the channel now. That is the owner's
 * decision, not an oversight — the sibling TravStats project's `#changelog`
 * is in the same state (topic says "Release notes mirrored from
 * CHANGELOG.md", no automation behind it). Do not add a `changelog` key here
 * to "fix" it.
 */

/**
 * Where announcements ask people to report back. Lives in the #BETA category,
 * which is role-restricted — the bot needs that category granted, or the
 * announcement will point at a channel its own readers may not see.
 */
export const FEEDBACK_CHANNEL = "beta-feedback";
