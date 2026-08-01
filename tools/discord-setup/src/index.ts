import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { createClient, loadEnv } from "./client.js";
import { parseLimit, runRead } from "./readChannel.js";
import { runReply } from "./replyThread.js";
import { runAnnounce, readRepoVersion, readRepoChangelog } from "./announce.js";
import { extractChangelogEntry } from "./changelog.js";
import { parseArgs } from "./args.js";
import { log } from "./log.js";

const USAGE =
  "Usage: tsx src/index.ts <read|reply|announce> [args]\n" +
  "  read                       list every channel in the guild\n" +
  "  read <channel> [limit]     print recent messages of a channel (default 20, max 100)\n" +
  "  reply <thread|channel> (<message…> | --file <path>) [--dry-run]\n" +
  "                             post into a forum thread or text channel\n" +
  "  announce <beta|rc|release> [version] [--notes-file <path> | --notes <text>] [--dry-run]\n" +
  "                             post a release announcement embed";

/**
 * Read a file passed via a CLI flag (`--file`, `--notes-file`), with an error
 * that names the flag and the path. Without this, an unreadable path surfaces
 * only through the generic top-level `FATAL:` handler as a bare ENOENT/EACCES
 * message that does not say which flag or file it came from.
 */
export function readFlagFile(flagName: string, path: string): string {
  try {
    return readFileSync(path, "utf8");
  } catch (err) {
    throw new Error(
      `Could not read ${flagName} file "${path}": ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

export type Command = "read" | "reply" | "announce";

/**
 * True for the three known subcommands, false for anything else — including
 * `undefined` (no command given at all). Extracted as its own predicate so
 * the command-before-environment ordering in `main()` (an unknown command
 * must print USAGE, not "DISCORD_BOT_TOKEN is missing") is unit-testable:
 * `main()` itself is not exported and runs as a module-level side effect at
 * the bottom of this file, so this pure boundary check is what stands in for
 * testing that behaviour directly.
 */
export function isKnownCommand(c: string | undefined): c is Command {
  return c === "read" || c === "reply" || c === "announce";
}

async function main(): Promise<void> {
  // The command is validated BEFORE the environment is loaded: an unknown
  // command with no `.env` present must print the usage text, not
  // "FATAL: DISCORD_BOT_TOKEN is missing…" — that points the reader at the
  // wrong problem.
  const command = process.argv[2];
  if (!isKnownCommand(command)) {
    log(USAGE);
    process.exitCode = 1;
    return;
  }

  if (command === "read") {
    // Routed through parseArgs like `reply`/`announce` even though `read`
    // takes no flags today — one extraction path for all three commands
    // instead of `read` alone still reading process.argv positionally.
    const { positional } = parseArgs(process.argv.slice(3), [], []);
    const channelName = positional[0] ?? null;
    const limit = parseLimit(positional[1]);
    const { token, guildId } = loadEnv();
    const client = createClient();
    await runRead(client, token, guildId, channelName, limit);
    return; // runRead owns login + destroy
  }

  if (command === "reply") {
    // Multi-line messages do not survive shell/npm argument passing reliably,
    // so `--file <path>` reads the message verbatim from a UTF-8 file. That is
    // the preferred form for anything with newlines.
    //
    // Flags are filtered out before positional arguments are read, so
    // `--dry-run` / `--file <path>` can appear anywhere on the command line —
    // `reply --dry-run general "msg"` and `reply general "msg" --dry-run`
    // parse identically.
    const { positional, values, flags } = parseArgs(
      process.argv.slice(3),
      ["--file"],
      ["--dry-run"],
    );
    const targetQuery = positional[0];
    const filePath = values["--file"];
    const message =
      filePath !== undefined
        ? readFlagFile("--file", filePath).replace(/\s+$/, "")
        : positional.slice(1).join(" ");

    if (!targetQuery || !message) {
      log("Usage: tsx src/index.ts reply <thread|channel> (<message…> | --file <path>) [--dry-run]");
      process.exitCode = 1;
      return;
    }
    // `reply --dry-run` still resolves the target against the live guild
    // (see runReply's docstring), so it needs credentials regardless.
    const { token, guildId } = loadEnv();
    const client = createClient();
    await runReply(client, token, guildId, targetQuery, message, flags["--dry-run"]);
    return; // runReply owns login + destroy
  }

  if (command === "announce") {
    // Same flag-placement rule as `reply`: flags are filtered out before the
    // positional arguments (type, version) are read.
    const { positional, values, flags } = parseArgs(
      process.argv.slice(3),
      ["--notes-file", "--notes"],
      ["--dry-run"],
    );
    const type = positional[0];
    if (type !== "beta" && type !== "rc" && type !== "release") {
      log(
        "Usage: tsx src/index.ts announce <beta|rc|release> [version] [--notes-file <path>|--notes <text>]",
      );
      process.exitCode = 1;
      return;
    }
    const version = positional[1] ?? readRepoVersion();
    if (!version) {
      log("No version given and backend/VERSION could not be read.");
      process.exitCode = 1;
      return;
    }

    // A beta ships from master HEAD, whose version has no CHANGELOG entry yet,
    // so `--notes-file <path>` (or inline `--notes "…"`) lets the announcement
    // carry real notes instead of the generic fallback.
    const notesFile = values["--notes-file"];
    const notesInline = values["--notes"];
    let notes: string | null;
    if (notesFile !== undefined) {
      notes = readFlagFile("--notes-file", notesFile).replace(/\s+$/, "");
    } else if (notesInline !== undefined) {
      notes = notesInline;
    } else {
      const changelog = readRepoChangelog();
      notes = changelog ? extractChangelogEntry(changelog, version) : null;
    }

    const dryRun = flags["--dry-run"];
    if (dryRun) {
      // A dry-run preview builds and prints the embed without ever calling
      // login() (see runAnnounce's docstring) — it needs neither the bot
      // token nor the guild id, so loadEnv() must not run ahead of this
      // branch. It used to, which meant previewing an announcement failed
      // outright without a working `.env`, even though the preview path
      // never connects to Discord at all.
      await runAnnounce(createClient(), "", "", type, version, notes, true);
      return;
    }

    const { token, guildId } = loadEnv();
    const client = createClient();
    await runAnnounce(client, token, guildId, type, version, notes, false);
    return; // runAnnounce owns login + destroy
  }
}

// `main()` runs only when this file is the CLI entry point (`tsx src/index.ts
// ...`), not when it is imported — e.g. by tests, which import `isKnownCommand`
// and `readFlagFile` above without wanting the CLI to actually execute against
// `process.argv`.
const isEntryPoint = process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntryPoint) {
  main().catch((err: unknown) => {
    log(`FATAL: ${err instanceof Error ? err.message : String(err)}`);
    process.exitCode = 1;
  });
}
