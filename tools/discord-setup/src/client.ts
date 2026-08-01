import { Client, GatewayIntentBits } from "discord.js";
import { config as loadDotenv } from "dotenv";

loadDotenv();

/**
 * Validate the two required variables. Pure — takes the environment as an
 * argument so it is testable without mutating `process.env`. The error names
 * the missing KEY and never the value: a thrown error can reach a log or a
 * transcript, and a token that has been in a transcript is a burnt token.
 */
export function parseEnv(env: Record<string, string | undefined>): {
  token: string;
  guildId: string;
} {
  const token = env.DISCORD_BOT_TOKEN;
  const guildId = env.DISCORD_GUILD_ID;
  if (!token) {
    throw new Error("DISCORD_BOT_TOKEN is missing — copy .env.example to .env and fill it in.");
  }
  if (!guildId) {
    throw new Error("DISCORD_GUILD_ID is missing — copy .env.example to .env and fill it in.");
  }
  return { token, guildId };
}

export function loadEnv(): { token: string; guildId: string } {
  return parseEnv(process.env);
}

/**
 * Guilds is the only intent this tool needs. It reads message bodies over the
 * REST API, which does not require the privileged MessageContent intent in
 * practice; if bodies ever come back empty, enable MessageContent in the Bot
 * tab of the Developer Portal (see README).
 */
export function createClient(): Client {
  return new Client({ intents: [GatewayIntentBits.Guilds] });
}
