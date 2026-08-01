import { ChannelType, Client, ForumChannel, GuildBasedChannel } from "discord.js";
import { log } from "./log.js";

const MAX_FORUM_THREADS = 15;

/**
 * One fetched message as a readable line. Falls back to a visible placeholder
 * when the content is empty — that happens when the bot lacks the privileged
 * MessageContent intent, and a blank line would misreport it as an empty
 * channel rather than a missing permission.
 */
export function formatMessage(authorTag: string, iso: string, content: string): string {
  const body = content.trim().length > 0 ? content : "(no text content)";
  return `[${iso}] ${authorTag}: ${body}`;
}

/** One channel as a line of the `read`-without-arguments listing. */
export function formatChannelLine(name: string, type: string, id: string): string {
  return `  #${name}  [${type}]  id ${id}`;
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
function typeName(channel: GuildBasedChannel): string {
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
    log(`#${forum.name} has no posts yet.`);
    return;
  }

  const shown = threads.slice(0, MAX_FORUM_THREADS);
  const suffix = threads.length > MAX_FORUM_THREADS ? ` of ${threads.length}` : "";
  log(`=== ${shown.length}${suffix} post(s) in forum #${forum.name} ===`);
  for (const thread of shown) {
    log(`\n--- post: "${thread.name}" ---`);
    const messages = await thread.messages.fetch({ limit: perThreadLimit });
    for (const message of [...messages.values()].reverse()) {
      log(formatMessage(message.author.tag, message.createdAt.toISOString(), message.content));
    }
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
        const guild = await (await client.guilds.fetch(guildId)).fetch();
        await guild.channels.fetch();
        const all = [...guild.channels.cache.values()].filter(
          (c): c is GuildBasedChannel => c !== null,
        );

        if (channelName === null) {
          await listChannels(all);
        } else {
          const needle = channelName.replace(/^#/, "").toLowerCase();
          const channel = all.find((c) => c.name.toLowerCase() === needle);
          if (!channel) {
            log(`Channel #${channelName} not found. Run \`npm run read\` to list every channel.`);
            process.exitCode = 1;
          } else if (channel instanceof ForumChannel) {
            await readForum(channel, limit);
          } else if (!channel.isTextBased()) {
            log(`#${channelName} is not a readable text or forum channel.`);
            process.exitCode = 1;
          } else {
            const messages = await channel.messages.fetch({ limit });
            if (messages.size === 0) {
              log(`#${channelName} has no messages yet.`);
            } else {
              log(`=== last ${messages.size} message(s) in #${channelName} (oldest first) ===`);
              for (const message of [...messages.values()].reverse()) {
                log(
                  formatMessage(
                    message.author.tag,
                    message.createdAt.toISOString(),
                    message.content,
                  ),
                );
              }
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
