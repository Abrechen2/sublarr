import { Client, ForumChannel, TextChannel, ThreadChannel } from "discord.js";
import { log } from "./log.js";

/** The minimum a resolver needs. Keeps the resolution logic testable. */
export interface ThreadLike {
  readonly id: string;
  readonly name: string;
}

export type NamedChannel = ThreadLike;

/**
 * Resolve a query to exactly one forum thread: an exact id first, then a
 * unique case-insensitive title substring. Returns null on a miss or an
 * ambiguity and logs the candidates, so the caller aborts instead of guessing
 * — a reply posted into the wrong public thread cannot be taken back.
 *
 * `diagnose` defaults to false because the caller tries threads FIRST and then
 * falls back to text channels: a thread miss is the normal path when replying
 * to #general, and logging "No forum thread matches" there would be noise
 * reported as an error. Ambiguity is always logged — that one is never normal.
 */
export function resolveThread<T extends ThreadLike>(
  threads: readonly T[],
  query: string,
  diagnose = false,
): T | null {
  const byId = threads.find((t) => t.id === query);
  if (byId) return byId;

  const needle = query.toLowerCase();
  const matches = threads.filter((t) => t.name.toLowerCase().includes(needle));
  if (matches.length === 1) return matches[0];

  if (matches.length > 1) {
    log(`"${query}" is ambiguous — ${matches.length} threads match. Use the id:`);
    for (const t of matches) log(`  - "${t.name}"  (id ${t.id})`);
  } else if (diagnose) {
    log(`No forum thread matches "${query}".`);
  }
  return null;
}

/**
 * Resolve a plain text channel by id or EXACT name. Deliberately stricter than
 * the thread lookup: a substring match would happily resolve "general" to
 * "#general-dev", and posting to the wrong public channel is not undoable in
 * any way that matters.
 */
export function resolveTextChannel<T extends NamedChannel>(
  channels: readonly T[],
  query: string,
): T | null {
  const needle = query.replace(/^#/, "").toLowerCase();
  return channels.find((c) => c.id === query || c.name.toLowerCase() === needle) ?? null;
}

/** Every forum post in the guild, active plus archived, best-effort per forum. */
async function collectForumThreads(forums: ForumChannel[]): Promise<ThreadChannel[]> {
  const threads: ThreadChannel[] = [];
  for (const forum of forums) {
    const active = await forum.threads.fetchActive().catch(() => null);
    const archived = await forum.threads.fetchArchived().catch(() => null);
    if (active) threads.push(...active.threads.values());
    if (archived) threads.push(...archived.threads.values());
  }
  return threads;
}

/**
 * Post a message into a forum thread or a text channel, then disconnect.
 * Forum threads are tried first — that is the common case — with a fallback to
 * an exactly-named text channel, because a follow-up owes the reporter an
 * answer wherever they raised it.
 *
 * With `dryRun` the function still logs in and resolves the target against the
 * live guild, so it can report what it would hit, but it returns before
 * `send()` — that is the operation that must not happen during a dry run.
 *
 * The returned promise settles only once the work is actually finished: it
 * resolves from inside the `finally`, after `client.destroy()`, not when
 * `client.login()` resolves. discord.js's `login()` resolves on the raw
 * gateway READY dispatch, which fires BEFORE the `clientReady` event this
 * function's work runs on — awaiting `login()` alone would return before the
 * reply has even started. A `login()` rejection (e.g. a bad token) rejects
 * this promise directly, since `clientReady` never fires in that case.
 */
export async function runReply(
  client: Client,
  token: string,
  guildId: string,
  targetQuery: string,
  message: string,
  dryRun: boolean,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    client.once("clientReady", async () => {
      try {
        const guild = await (await client.guilds.fetch(guildId)).fetch();
        await guild.channels.fetch();

        const forums = [...guild.channels.cache.values()].filter(
          (c): c is ForumChannel => c instanceof ForumChannel,
        );
        const texts = [...guild.channels.cache.values()].filter(
          (c): c is TextChannel => c instanceof TextChannel,
        );
        const threads = await collectForumThreads(forums);

        const target: ThreadChannel | TextChannel | null =
          resolveThread(threads, targetQuery) ?? resolveTextChannel(texts, targetQuery);

        if (!target) {
          log(`Nothing matches "${targetQuery}". Run \`npm run read\` to list channels.`);
          process.exitCode = 1;
          return;
        }

        if (dryRun) {
          log(`[dry-run] would post to "${target.name}" (id ${target.id}):`);
          log(`[dry-run] ${message}`);
          return;
        }

        const sent = await target.send(message);
        log(`Posted to "${target.name}" (id ${target.id}): ${sent.url}`);
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
