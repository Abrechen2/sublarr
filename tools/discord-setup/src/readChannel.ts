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
 * archived, capped) and print each post's messages. Archived threads are
 * fetched best-effort: one missing permission must not abort the whole read.
 */
async function readForum(forum: ForumChannel, perThreadLimit: number): Promise<void> {
  const active = await forum.threads.fetchActive();
  const archived = await forum.threads.fetchArchived().catch(() => null);
  const threads = [...active.threads.values(), ...(archived ? [...archived.threads.values()] : [])];
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
 */
export async function runRead(
  client: Client,
  token: string,
  guildId: string,
  channelName: string | null,
  limit: number,
): Promise<void> {
  client.once("clientReady", async () => {
    try {
      const guild = await (await client.guilds.fetch(guildId)).fetch();
      await guild.channels.fetch();
      const all = [...guild.channels.cache.values()].filter(
        (c): c is GuildBasedChannel => c !== null,
      );

      if (channelName === null) {
        await listChannels(all);
        return;
      }

      const needle = channelName.replace(/^#/, "").toLowerCase();
      const channel = all.find((c) => c.name.toLowerCase() === needle);
      if (!channel) {
        log(`Channel #${channelName} not found. Run \`npm run read\` to list every channel.`);
        process.exitCode = 1;
        return;
      }
      if (channel instanceof ForumChannel) {
        await readForum(channel, limit);
        return;
      }
      if (!channel.isTextBased()) {
        log(`#${channelName} is not a readable text or forum channel.`);
        process.exitCode = 1;
        return;
      }

      const messages = await channel.messages.fetch({ limit });
      if (messages.size === 0) {
        log(`#${channelName} has no messages yet.`);
        return;
      }
      log(`=== last ${messages.size} message(s) in #${channelName} (oldest first) ===`);
      for (const message of [...messages.values()].reverse()) {
        log(formatMessage(message.author.tag, message.createdAt.toISOString(), message.content));
      }
    } catch (err) {
      log(`ERROR: ${err instanceof Error ? err.message : String(err)}`);
      process.exitCode = 1;
    } finally {
      await client.destroy();
    }
  });

  await client.login(token);
}
