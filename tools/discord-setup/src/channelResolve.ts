import { ChannelType } from "discord.js";
import { log } from "./log.js";

/** The minimum a resolver needs to identify and describe a channel. */
export interface NamedTypedChannel {
  readonly id: string;
  readonly name: string;
  readonly type: ChannelType;
}

/**
 * Channel types whose message history `read` and `announce` actually work
 * with: plain text, announcement channels, forums (posts are read/posted via
 * their threads), and threads themselves.
 *
 * Deliberately excludes voice/stage channels. discord.js's `isTextBased()`
 * returns true for those too (every voice channel has a text chat), but they
 * do not hold the conversations these commands care about — and a lowercase
 * name collision between a text and a voice channel is not hypothetical: this
 * guild has exactly one, `#general` (text) vs `#General` (voice), and the
 * naive `.find()` this replaced picked the voice channel and reported the
 * community's main text channel as empty.
 */
const MESSAGE_CAPABLE_TYPES: ReadonlySet<ChannelType> = new Set([
  ChannelType.GuildText,
  ChannelType.GuildAnnouncement,
  ChannelType.GuildForum,
  ChannelType.PublicThread,
  ChannelType.PrivateThread,
  ChannelType.AnnouncementThread,
]);

export function isMessageCapable(channel: { type: ChannelType }): boolean {
  return MESSAGE_CAPABLE_TYPES.has(channel.type);
}

/**
 * Resolve a channel by exact id or exact case-insensitive name, restricted to
 * message-capable channel types. Aborts (returns null and logs every
 * candidate with its id and type) on an ambiguous match instead of picking
 * one silently — the same "exact beats guessing" rule `resolveReplyTarget`
 * already applies to `reply`, shared here for `read` and `announce`.
 *
 * `typeName` is injected rather than imported to avoid a circular import
 * with `readChannel.ts`, which both defines `typeName` and depends on this
 * module.
 */
export function resolveChannelByExactName<T extends NamedTypedChannel>(
  channels: readonly T[],
  query: string,
  typeName: (channel: T) => string,
): T | null {
  const needle = query.replace(/^#/, "").toLowerCase();
  const candidates = channels.filter(isMessageCapable);
  const matches = candidates.filter((c) => c.id === query || c.name.toLowerCase() === needle);

  if (matches.length === 1) return matches[0];

  if (matches.length > 1) {
    log(`"${query}" is ambiguous — ${matches.length} channels match. Use the id:`);
    for (const m of matches) log(`  - "${m.name}"  (${typeName(m)}, id ${m.id})`);
  }

  return null;
}
