import { readFileSync } from "node:fs";
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
function readFlagFile(flagName: string, path: string): string {
  try {
    return readFileSync(path, "utf8");
  } catch (err) {
    throw new Error(
      `Could not read ${flagName} file "${path}": ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

async function main(): Promise<void> {
  // The command is validated BEFORE the environment is loaded: an unknown
  // command with no `.env` present must print the usage text, not
  // "FATAL: DISCORD_BOT_TOKEN is missing…" — that points the reader at the
  // wrong problem.
  const command = process.argv[2];
  if (command !== "read" && command !== "reply" && command !== "announce") {
    log(USAGE);
    process.exitCode = 1;
    return;
  }

  const dryRun = process.argv.includes("--dry-run");
  const { token, guildId } = loadEnv();
  const client = createClient();

  if (command === "read") {
    const channelName = process.argv[3] ?? null;
    const limit = parseLimit(process.argv[4]);
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
    const { positional, values } = parseArgs(process.argv.slice(3), ["--file"], ["--dry-run"]);
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
    await runReply(client, token, guildId, targetQuery, message, dryRun);
    return; // runReply owns login + destroy
  }

  if (command === "announce") {
    // Same flag-placement rule as `reply`: flags are filtered out before the
    // positional arguments (type, version) are read.
    const { positional, values } = parseArgs(
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

    await runAnnounce(client, token, guildId, type, version, notes, dryRun);
    return; // runAnnounce owns login + destroy
  }
}

main().catch((err: unknown) => {
  log(`FATAL: ${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});
