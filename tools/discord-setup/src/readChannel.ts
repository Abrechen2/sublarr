import { ChannelType, Client, Collection, ForumChannel, GuildBasedChannel, Message } from "discord.js";
import { resolveChannelByExactName } from "./channelResolve.js";
import { log } from "./log.js";

const MAX_FORUM_THREADS = 15;

const BYTE_UNITS = ["B", "KB", "MB", "GB"] as const;

/**
 * A file size for display. `size` arrives from the Discord API, so a negative
 * or non-finite value is possible and must not render as a bogus unit string.
 * Values past the largest unit stay in that unit — an oversized number is
 * still readable, an invented unit is not.
 */
export function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size < 0) {
    return "unknown size";
  }
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value = value / 1024;
    unit += 1;
  }
  // One decimal, but only when it carries information: "1.5 KB", not "2.0 KB".
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
  return `${rendered} ${BYTE_UNITS[unit]}`;
}

/** The attachment fields this module renders — a structural subset of discord.js's `Attachment`. */
export interface MessageAttachment {
  name: string;
  size: number;
  url: string;
}

/** The embed fields this module renders — a structural subset of discord.js's `Embed`. */
export interface MessageEmbed {
  title?: string | null;
  description?: string | null;
  url?: string | null;
  fields?: readonly { name: string; value: string }[];
  footer?: { text: string } | null;
}

/**
 * One embed as indented lines. Bot posts in #announcements and #changelog carry
 * their entire content in an embed and none in `content`, so the release
 * history was unreadable from the CLI without this.
 *
 * An embed with nothing renderable still yields a line: it may hold only an
 * image or an author block, and emitting nothing would recreate exactly the
 * "message looks empty" bug this exists to fix. Descriptions are printed in
 * full rather than truncated — reading them is the point, and `limit` already
 * bounds how many messages come back.
 */
export function formatEmbed(embed: MessageEmbed): string[] {
  const lines: string[] = [];
  if (embed.title) {
    lines.push(`  embed: ${embed.title}`);
  }
  if (embed.url) {
    lines.push(`  embed url: ${embed.url}`);
  }
  if (embed.description) {
    // Blank lines stay blank rather than becoming indent-only whitespace.
    lines.push(...embed.description.split("\n").map((l) => (l.length > 0 ? `    ${l}` : "")));
  }
  for (const field of embed.fields ?? []) {
    lines.push(`  embed field: ${field.name} = ${field.value}`);
  }
  if (embed.footer?.text) {
    lines.push(`  embed footer: ${embed.footer.text}`);
  }
  return lines.length > 0 ? lines : ["  embed: (empty)"];
}

/**
 * The placeholder for a message with no text. Which one is used carries
 * diagnostic weight: Discord gates `content`, `attachments` and `embeds` behind
 * the same privileged MessageContent intent, so anything visible here proves
 * the intent is on and the message simply had no text. Only the bare
 * "(no text content)" is ambiguous enough to suspect the missing intent.
 */
function emptyBodyPlaceholder(hasAttachments: boolean, hasEmbeds: boolean): string {
  if (hasAttachments && hasEmbeds) {
    return "(attachment and embed only)";
  }
  if (hasAttachments) {
    return "(attachment only)";
  }
  if (hasEmbeds) {
    return "(embed only)";
  }
  return "(no text content)";
}

/**
 * One fetched message as readable output: a header line, then one indented
 * line per attachment, then the embeds. Both are rendered because they
 * routinely carry the entire point of a message — a support-export ZIP in
 * #bug-report, or a whole release note in #announcements — and dropping them
 * made such a message read as if nothing usable had been sent.
 *
 * Empty content gets a visible placeholder rather than a blank line; see
 * `emptyBodyPlaceholder` for why the wording differs per case.
 */
export function formatMessage(
  authorTag: string,
  iso: string,
  content: string,
  attachments: readonly MessageAttachment[] = [],
  embeds: readonly MessageEmbed[] = [],
): string {
  const body =
    content.trim().length > 0
      ? content
      : emptyBodyPlaceholder(attachments.length > 0, embeds.length > 0);
  const lines = [
    `[${iso}] ${authorTag}: ${body}`,
    ...attachments.map((a) => `  attachment: ${a.name} (${formatBytes(a.size)}) ${a.url}`),
    ...embeds.flatMap(formatEmbed),
  ];
  return lines.join("\n");
}

/** One channel as a line of the `read`-without-arguments listing. */
export function formatChannelLine(name: string, type: string, id: string): string {
  return `  #${name}  [${type}]  id ${id}`;
}

/** Print a fetched message page oldest-first — shared by the channel and forum-thread readers. */
function logMessagesOldestFirst(messages: Collection<string, Message>): void {
  for (const message of [...messages.values()].reverse()) {
    const attachments = [...message.attachments.values()].map((a) => ({
      name: a.name,
      size: a.size,
      url: a.url,
    }));
    const embeds = message.embeds.map((e) => ({
      title: e.title,
      description: e.description,
      url: e.url,
      fields: e.fields.map((f) => ({ name: f.name, value: f.value })),
      footer: e.footer ? { text: e.footer.text } : null,
    }));
    log(
      formatMessage(
        message.author.tag,
        message.createdAt.toISOString(),
        message.content,
        attachments,
        embeds,
      ),
    );
  }
}

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;

/**
 * Parse the CLI `limit` argument. Missing, non-numeric, non-integer, or
 * below-minimum input falls back to the default; above-maximum input is
 * clamped to the maximum rather than silently falling back to the default —
 * a clamp is visible in the result count, a silent fallback isn't.
 */
export function parseLimit(raw: string | undefined): number {
  if (raw === undefined) {
    return DEFAULT_LIMIT;
  }
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return DEFAULT_LIMIT;
  }
  return Math.min(parsed, MAX_LIMIT);
}

/** Human-readable channel type, used only by the listing. */
export function typeName(channel: GuildBasedChannel): string {
  switch (channel.type) {
    case ChannelType.GuildText:
      return "text";
    case ChannelType.GuildForum:
      return "forum";
    case ChannelType.GuildAnnouncement:
      return "announcement";
    case ChannelType.GuildVoice:
      return "voice";
    case ChannelType.GuildCategory:
      return "category";
    case ChannelType.PublicThread:
    case ChannelType.PrivateThread:
    case ChannelType.AnnouncementThread:
      return "thread";
    default:
      return `type-${channel.type}`;
  }
}

/**
 * List every channel in the guild. This is the discovery path: channel names
 * are not knowable ahead of time, and `read`/`reply`/`announce` all address
 * channels by name.
 */
async function listChannels(channels: GuildBasedChannel[]): Promise<void> {
  const sorted = [...channels].sort((a, b) => a.name.localeCompare(b.name));
  log(`=== ${sorted.length} channel(s) in the guild ===`);
  for (const channel of sorted) {
    log(formatChannelLine(channel.name, typeName(channel), channel.id));
  }
}

/**
 * A forum holds its posts as threads, so enumerate the threads (active plus
 * archived, capped) and print each post's messages. Fetching either list is
 * best-effort: a permission denial, rate limit or transient network error on
 * one must not abort the whole read — but it must be visible, not silent, or
 * the listing under-reports posts with no way to tell "there are only N" from
 * "fetching more failed."
 */
async function readForum(forum: ForumChannel, perThreadLimit: number): Promise<void> {
  const active = await forum.threads.fetchActive().catch((err: unknown) => {
    log(
      `WARNING: failed to fetch active threads in #${forum.name}: ${err instanceof Error ? err.message : String(err)}`,
    );
    return null;
  });
  const archived = await forum.threads.fetchArchived().catch((err: unknown) => {
    log(
      `WARNING: failed to fetch archived threads in #${forum.name}: ${err instanceof Error ? err.message : String(err)}`,
    );
    return null;
  });
  const threads = [
    ...(active ? [...active.threads.values()] : []),
    ...(archived ? [...archived.threads.values()] : []),
  ];
  if (threads.length === 0) {
    log(`#${forum.name} (id ${forum.id}) has no posts yet.`);
    return;
  }

  const shown = threads.slice(0, MAX_FORUM_THREADS);
  const suffix = threads.length > MAX_FORUM_THREADS ? ` of ${threads.length}` : "";
  log(`=== ${shown.length}${suffix} post(s) in forum #${forum.name} (id ${forum.id}) ===`);
  for (const thread of shown) {
    log(`\n--- post: "${thread.name}" ---`);
    const messages = await thread.messages.fetch({ limit: perThreadLimit });
    logMessagesOldestFirst(messages);
  }
}

/**
 * On-demand reader: log in, print either the channel listing or one channel's
 * recent messages oldest-first, then disconnect. One shot per invocation.
 *
 * The returned promise settles only once the work is actually finished: it
 * resolves from inside the `finally`, after `client.destroy()`, not when
 * `client.login()` resolves. discord.js's `login()` resolves on the raw
 * gateway READY dispatch, which fires BEFORE the `clientReady` event this
 * function's work runs on — awaiting `login()` alone would return before the
 * read has even started. A `login()` rejection (e.g. a bad token) rejects
 * this promise directly, since `clientReady` never fires in that case.
 */
export async function runRead(
  client: Client,
  token: string,
  guildId: string,
  channelName: string | null,
  limit: number,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    client.once("clientReady", async () => {
      try {
        const guild = await client.guilds.fetch(guildId);
        await guild.channels.fetch();
        const all = [...guild.channels.cache.values()].filter(
          (c): c is GuildBasedChannel => c !== null,
        );

        if (channelName === null) {
          await listChannels(all);
        } else {
          // Restricted to message-capable types (text, announcement, forum,
          // thread) and aborts on an ambiguous match — see channelResolve.ts.
          // Plain `isTextBased()` is not enough here: voice channels satisfy
          // it too, and this guild has a real lowercase collision, `#general`
          // (text) vs `#General` (voice), that a type-agnostic lookup picks
          // wrong.
          const channel = resolveChannelByExactName(all, channelName, typeName);
          if (!channel) {
            log(
              `Channel #${channelName} not found or ambiguous. Run \`npm run read\` to list every channel.`,
            );
            process.exitCode = 1;
          } else if (channel instanceof ForumChannel) {
            await readForum(channel, limit);
          } else if (!channel.isTextBased()) {
            log(`#${channel.name} (id ${channel.id}) is not a readable text or forum channel.`);
            process.exitCode = 1;
          } else {
            const messages = await channel.messages.fetch({ limit });
            if (messages.size === 0) {
              log(`#${channel.name} (id ${channel.id}) has no messages yet.`);
            } else {
              log(
                `=== last ${messages.size} message(s) in #${channel.name} (id ${channel.id}, oldest first) ===`,
              );
              logMessagesOldestFirst(messages);
            }
          }
        }
      } catch (err) {
        log(`ERROR: ${err instanceof Error ? err.message : String(err)}`);
        process.exitCode = 1;
      } finally {
        await client.destroy();
        resolve();
      }
    });

    client.login(token).catch((err: unknown) => {
      reject(err instanceof Error ? err : new Error(String(err)));
    });
  });
}
