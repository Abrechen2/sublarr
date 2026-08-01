import { createClient, loadEnv } from "./client.js";
import { runRead } from "./readChannel.js";
import { log } from "./log.js";

const USAGE =
  "Usage: tsx src/index.ts <read> [args]\n" +
  "  read                       list every channel in the guild\n" +
  "  read <channel> [limit]     print recent messages of a channel (default 20, max 100)";

async function main(): Promise<void> {
  const command = process.argv[2];
  const { token, guildId } = loadEnv();
  const client = createClient();

  if (command === "read") {
    const channelName = process.argv[3] ?? null;
    const parsed = Number(process.argv[4] ?? "20");
    const limit = Number.isInteger(parsed) && parsed > 0 && parsed <= 100 ? parsed : 20;
    await runRead(client, token, guildId, channelName, limit);
    return; // runRead owns login + destroy
  }

  log(USAGE);
  process.exitCode = 1;
}

main().catch((err: unknown) => {
  log(`FATAL: ${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});
