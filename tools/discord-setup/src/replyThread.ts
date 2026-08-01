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

/** True when `item` matches `query` by id, or by exact name once a leading `#` is stripped. */
function isExactMatch(item: ThreadLike, query: string): boolean {
  const needle = query.replace(/^#/, "").toLowerCase();
  return item.id === query || item.name.toLowerCase() === needle;
}

/** One exact-match candidate, tagged with which collection it came from — needed to render it in an ambiguity report. */
export interface ExactMatch<T extends ThreadLike> {
  readonly kind: "thread" | "channel";
  readonly value: T;
}

/**
 * Every exact match (by id or exact name) across both threads and channels
 * for one query. Exported as its own pure step because "exact beats fuzzy" is
 * exactly the rule the safety rails depend on: a query that exact-matches a
 * text channel must not lose to a thread that only substring-matches it.
 */
export function findExactMatches<T extends ThreadLike, U extends NamedChannel>(
  threads: readonly T[],
  channels: readonly U[],
  query: string,
): Array<ExactMatch<T> | ExactMatch<U>> {
  return [
    ...threads.filter((t) => isExactMatch(t, query)).map((value) => ({ kind: "thread" as const, value })),
    ...channels.filter((c) => isExactMatch(c, query)).map((value) => ({ kind: "channel" as const, value })),
  ];
}

/**
 * Resolve the reply target across both forum threads and text channels, exact
 * matches first. This is the actual safety-critical ordering:
 *
 * 1. Every exact match (by id or exact name) across BOTH collections is
 *    collected first. Exactly one -> that is the target, regardless of
 *    whether a thread also substring-matches the same query.
 * 2. More than one exact match (e.g. a thread named "support" AND a channel
 *    "#support") aborts and lists every candidate — picking one here would be
 *    the same kind of guess the substring rules exist to prevent.
 * 3. Only when there is no exact match anywhere does a unique thread-title
 *    substring win (the existing `resolveThread` behaviour, unchanged).
 *
 * Without this ordering, a thread that only substring-matches (e.g. "Support
 * ticket: xyz issue") could beat a text channel that matches exactly
 * (`#support`), since the fuzzy resolver ran before the exact one. That
 * silently misdirects a reply into an unrelated public thread.
 */
export function resolveReplyTarget<T extends ThreadLike, U extends NamedChannel>(
  threads: readonly T[],
  channels: readonly U[],
  query: string,
): T | U | null {
  const exact = findExactMatches(threads, channels, query);
  if (exact.length === 1) return exact[0].value;

  if (exact.length > 1) {
    log(`"${query}" is ambiguous — ${exact.length} exact matches. Use the id:`);
    for (const m of exact) log(`  - "${m.value.name}"  (${m.kind}, id ${m.value.id})`);
    return null;
  }

  return resolveThread(threads, query);
}

/**
 * Every forum post in the guild, active plus archived, best-effort per forum.
 * A fetch failure (permission, rate limit, transient network error) drops
 * that forum's threads from the search rather than aborting the whole reply,
 * but it is logged as a WARNING naming the forum and the error — silently
 * dropping threads would make a genuine match report as "Nothing matches"
 * with no hint that the search was incomplete.
 */
async function collectForumThreads(forums: ForumChannel[]): Promise<ThreadChannel[]> {
  const threads: ThreadChannel[] = [];
  for (const forum of forums) {
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
        const guild = await client.guilds.fetch(guildId);
        await guild.channels.fetch();

        const forums = [...guild.channels.cache.values()].filter(
          (c): c is ForumChannel => c instanceof ForumChannel,
        );
        const texts = [...guild.channels.cache.values()].filter(
          (c): c is TextChannel => c instanceof TextChannel,
        );
        const threads = await collectForumThreads(forums);

        const target: ThreadChannel | TextChannel | null = resolveReplyTarget(
          threads,
          texts,
          targetQuery,
        );

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
