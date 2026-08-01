import { readFileSync } from "node:fs";
import { createClient, loadEnv } from "./client.js";
import { parseLimit, runRead } from "./readChannel.js";
import { runReply } from "./replyThread.js";
import { runAnnounce, readRepoVersion, readRepoChangelog, AnnounceType } from "./announce.js";
import { extractChangelogEntry } from "./changelog.js";
import { log } from "./log.js";

const USAGE =
  "Usage: tsx src/index.ts <read|reply|announce> [args]\n" +
  "  read                       list every channel in the guild\n" +
  "  read <channel> [limit]     print recent messages of a channel (default 20, max 100)\n" +
  "  reply <thread|channel> (<message…> | --file <path>) [--dry-run]\n" +
  "                             post into a forum thread or text channel\n" +
  "  announce <beta|rc|release> [version] [--notes-file <path> | --notes <text>] [--dry-run]\n" +
  "                             post a release announcement embed";

async function main(): Promise<void> {
  const command = process.argv[2];
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
    const targetQuery = process.argv[3];
    // Multi-line messages do not survive shell/npm argument passing reliably,
    // so `--file <path>` reads the message verbatim from a UTF-8 file. That is
    // the preferred form for anything with newlines.
    const fileIdx = process.argv.indexOf("--file");
    const message =
      fileIdx !== -1 && process.argv[fileIdx + 1]
        ? readFileSync(process.argv[fileIdx + 1], "utf8").replace(/\s+$/, "")
        : process.argv
            .slice(4)
            .filter((a) => a !== "--dry-run")
            .join(" ");

    if (!targetQuery || !message) {
      log("Usage: tsx src/index.ts reply <thread|channel> (<message…> | --file <path>) [--dry-run]");
      process.exitCode = 1;
      return;
    }
    await runReply(client, token, guildId, targetQuery, message, dryRun);
    return; // runReply owns login + destroy
  }

  if (command === "announce") {
    const type = process.argv[3];
    if (type !== "beta" && type !== "rc" && type !== "release") {
      log("Usage: tsx src/index.ts announce <beta|rc|release> [version] [--notes-file <path> | --notes <text>]");
      process.exitCode = 1;
      return;
    }
    const versionArg = process.argv[4];
    const version = versionArg && !versionArg.startsWith("--") ? versionArg : readRepoVersion();
    if (!version) {
      log("No version given and backend/VERSION could not be read.");
      process.exitCode = 1;
      return;
    }

    // A beta ships from master HEAD, whose version has no CHANGELOG entry yet,
    // so `--notes-file <path>` (or inline `--notes "…"`) lets the announcement
    // carry real notes instead of the generic fallback.
    const notesFileIdx = process.argv.indexOf("--notes-file");
    const notesInlineIdx = process.argv.indexOf("--notes");
    let notes: string | null;
    if (notesFileIdx !== -1 && process.argv[notesFileIdx + 1]) {
      notes = readFileSync(process.argv[notesFileIdx + 1], "utf8").replace(/\s+$/, "");
    } else if (notesInlineIdx !== -1 && process.argv[notesInlineIdx + 1]) {
      notes = process.argv[notesInlineIdx + 1];
    } else {
      const changelog = readRepoChangelog();
      notes = changelog ? extractChangelogEntry(changelog, version) : null;
    }

    await runAnnounce(client, token, guildId, type as AnnounceType, version, notes, dryRun);
    return; // runAnnounce owns login + destroy
  }

  log(USAGE);
  process.exitCode = 1;
}

main().catch((err: unknown) => {
  log(`FATAL: ${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});
