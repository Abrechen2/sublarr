import { Client, EmbedBuilder } from "discord.js";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { ANNOUNCE_CHANNELS, FEEDBACK_CHANNEL } from "./channels.js";
import { log } from "./log.js";

// The three lanes mirror the deployment tiers (CLAUDE.local.md):
//   beta    — `:beta` from master HEAD, port 5767, internal dogfooding
//   rc      — `X.Y.Z-rc.N` on the prod-mirror RC instance, port 5766
//   release — promoted `X.Y.Z` on prod, port 5765
export type AnnounceType = "beta" | "rc" | "release";

const REPO_URL = "https://github.com/abrechen2/sublarr";
const MAX_NOTES = 3500; // a Discord embed description caps at 4096

interface AnnounceStyle {
  readonly channel: string;
  readonly color: number;
  readonly title: (v: string) => string;
  readonly intro: string;
}

const STYLE: Record<AnnounceType, AnnounceStyle> = {
  beta: {
    channel: ANNOUNCE_CHANNELS.beta,
    color: 0x8b6fd4,
    title: (v) => `🧪 Beta ${v}`,
    intro:
      "A new beta build from the forward dev line is live. Expect rough edges — " +
      `report anything odd in **#${FEEDBACK_CHANNEL}**.`,
  },
  rc: {
    channel: ANNOUNCE_CHANNELS.rc,
    color: 0xf0a947,
    title: (v) => `🚦 Release Candidate ${v}`,
    intro:
      "A release candidate has been validated against a copy of production data " +
      `and is lined up to ship. Final testing — report anything in **#${FEEDBACK_CHANNEL}**.`,
  },
  release: {
    channel: ANNOUNCE_CHANNELS.release,
    color: 0x1db8d4,
    title: (v) => `🚀 Sublarr ${v} released`,
    intro: "A new version is out.",
  },
};

const here = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(here, "..", "..", "..");

export function readRepoVersion(): string | null {
  const path = join(REPO_ROOT, "backend", "VERSION");
  return existsSync(path) ? readFileSync(path, "utf8").trim() : null;
}

export function readRepoChangelog(): string | null {
  const path = join(REPO_ROOT, "CHANGELOG.md");
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

export function channelForType(type: AnnounceType): string {
  return STYLE[type].channel;
}

/**
 * Build the announcement embed. Pure — no I/O, no network — so the copy, the
 * truncation and the tag link are all unit-testable.
 *
 * The tag link keeps the FULL version including any `-rc.N`, unlike the
 * changelog lookup which strips it: the GitHub tag for an RC really is
 * `v1.10.0-rc.2`.
 */
export function buildAnnounceEmbed(
  type: AnnounceType,
  version: string,
  notes: string | null,
): EmbedBuilder {
  const style = STYLE[type];
  const body = notes && notes.trim().length > 0 ? notes.trim() : "See the changelog for details.";
  const truncated = body.length > MAX_NOTES ? `${body.slice(0, MAX_NOTES)}\n…` : body;
  const releaseUrl = `${REPO_URL}/releases/tag/v${version}`;

  return new EmbedBuilder()
    .setTitle(style.title(version))
    .setColor(style.color)
    .setDescription(`${style.intro}\n\n${truncated}\n\n🔗 ${releaseUrl}`)
    .setFooter({ text: `sublarr-release-${version}` });
}

/**
 * Post the announcement embed, then disconnect.
 *
 * A dry run returns BEFORE `login()`. It opens no gateway connection and
 * reaches no `send`. The target channel is a constant, so unlike `reply`
 * there is nothing to resolve live and no reason to connect at all.
 *
 * The live path settles the returned promise only once the work is actually
 * finished: it resolves from inside the `finally`, after `client.destroy()`,
 * not when `client.login()` resolves. discord.js's `login()` resolves on the
 * raw gateway READY dispatch, which fires BEFORE the `clientReady` event this
 * function's work runs on — awaiting `login()` alone would return before the
 * announcement has even been posted. A `login()` rejection (e.g. a bad token)
 * rejects this promise directly, since `clientReady` never fires in that case.
 */
export async function runAnnounce(
  client: Client,
  token: string,
  guildId: string,
  type: AnnounceType,
  version: string,
  notes: string | null,
  dryRun: boolean,
): Promise<void> {
  const channelName = channelForType(type);

  if (dryRun) {
    const embed = buildAnnounceEmbed(type, version, notes).toJSON();
    log("=== DRY RUN — nothing was posted ===");
    log(`channel: #${channelName}`);
    log(`title:   ${embed.title ?? "(none)"}`);
    log("--- description ---");
    log(embed.description ?? "(none)");
    return;
  }

  return new Promise<void>((resolve, reject) => {
    client.once("clientReady", async () => {
      try {
        const guild = await client.guilds.fetch(guildId);
        await guild.channels.fetch();
        const channel = guild.channels.cache.find((c) => c.name === channelName);
        if (!channel || !channel.isTextBased()) {
          log(`Target channel #${channelName} not found or not a text channel.`);
          process.exitCode = 1;
          return;
        }
        await channel.send({ embeds: [buildAnnounceEmbed(type, version, notes)] });
        log(`announced ${type} ${version} in #${channelName}`);
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
