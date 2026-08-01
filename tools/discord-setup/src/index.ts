import { readFileSync } from "node:fs";
import { createClient, loadEnv } from "./client.js";
import { parseLimit, runRead } from "./readChannel.js";
import { runReply } from "./replyThread.js";
import { log } from "./log.js";

const USAGE =
  "Usage: tsx src/index.ts <read|reply> [args]\n" +
  "  read                       list every channel in the guild\n" +
  "  read <channel> [limit]     print recent messages of a channel (default 20, max 100)\n" +
  "  reply <thread|channel> (<message…> | --file <path>) [--dry-run]\n" +
  "                             post into a forum thread or text channel";

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

  log(USAGE);
  process.exitCode = 1;
}

main().catch((err: unknown) => {
  log(`FATAL: ${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});
