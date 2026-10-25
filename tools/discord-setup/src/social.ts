import { log } from "./log.js";
import {
  buildBlueskyPost,
  buildMastodonText,
  type SocialType,
  charCount,
  graphemeCount,
} from "./socialText.js";

export type SocialTarget = "mastodon" | "bluesky";
export type Target = "discord" | SocialTarget;

export const ALL_TARGETS: readonly Target[] = ["discord", "mastodon", "bluesky"];

type Env = Readonly<Record<string, string | undefined>>;

const REQUIRED_ENV: Record<SocialTarget, readonly string[]> = {
  mastodon: ["MASTODON_INSTANCE", "MASTODON_ACCESS_TOKEN"],
  bluesky: ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"],
};

const REQUEST_TIMEOUT_MS = 15_000;

/** Parse `--targets a,b`. Throws on an unknown name; default is discord only. */
export function parseTargets(raw: string | undefined): Target[] {
  if (raw === undefined) return ["discord"];
  const names = raw.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean);
  const unknown = names.filter((n) => !ALL_TARGETS.includes(n as Target));
  if (unknown.length > 0 || names.length === 0) {
    throw new Error(
      `Unknown --targets value "${unknown.join(",") || raw}". Valid: ${ALL_TARGETS.join(", ")}.`,
    );
  }
  return [...new Set(names)] as Target[];
}

/** Names (never values) of the required variables that are unset or empty. */
export function missingEnv(target: SocialTarget, env: Env): string[] {
  return REQUIRED_ENV[target].filter((k) => !env[k] || env[k]!.trim() === "");
}

async function postJson(
  url: string,
  headers: Record<string, string>,
  body: unknown,
): Promise<Record<string, unknown>> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const detail = typeof data.error === "string" ? data.error : typeof data.message === "string" ? data.message : "";
    throw new Error(`HTTP ${res.status} from ${new URL(url).host}${detail ? `: ${detail.slice(0, 200)}` : ""}`);
  }
  return data;
}

export async function postMastodon(text: string, env: Env, version: string): Promise<string> {
  const instance = env.MASTODON_INSTANCE!.trim().replace(/\/+$/, "");
  if (!/^https:\/\//.test(instance)) {
    throw new Error("MASTODON_INSTANCE must start with https://");
  }
  const data = await postJson(
    `${instance}/api/v1/statuses`,
    {
      Authorization: `Bearer ${env.MASTODON_ACCESS_TOKEN}`,
      // Makes an accidental re-run of the same announcement a no-op.
      "Idempotency-Key": `sublarr-release-${version}`,
    },
    { status: text, visibility: "public", language: "en" },
  );
  return typeof data.url === "string" ? data.url : "(no url returned)";
}

export async function postBluesky(
  post: ReturnType<typeof buildBlueskyPost>,
  env: Env,
): Promise<string> {
  const service = (env.BLUESKY_SERVICE?.trim() || "https://bsky.social").replace(/\/+$/, "");
  const session = await postJson(`${service}/xrpc/com.atproto.server.createSession`, {}, {
    identifier: env.BLUESKY_HANDLE,
    password: env.BLUESKY_APP_PASSWORD,
  });
  const jwt = session.accessJwt;
  const did = session.did;
  if (typeof jwt !== "string" || typeof did !== "string") {
    throw new Error("Bluesky createSession returned no accessJwt/did.");
  }
  const created = await postJson(
    `${service}/xrpc/com.atproto.repo.createRecord`,
    { Authorization: `Bearer ${jwt}` },
    {
      repo: did,
      collection: "app.bsky.feed.post",
      record: {
        $type: "app.bsky.feed.post",
        text: post.text,
        facets: post.facets,
        embed: post.embed,
        langs: ["en"],
        createdAt: new Date().toISOString(),
      },
    },
  );
  return typeof created.uri === "string" ? created.uri : "(no uri returned)";
}

function previewMastodon(text: string): void {
  log(`--- mastodon (${charCount(text)}/500 chars) ---`);
  log(text);
}

function previewBluesky(post: ReturnType<typeof buildBlueskyPost>): void {
  log(`--- bluesky (${graphemeCount(post.text)}/300 graphemes) ---`);
  log(post.text);
  log(`facets: ${JSON.stringify(post.facets)}`);
  log(`link card: ${JSON.stringify(post.embed.external)}`);
}

/**
 * Render (dry run) or post to the given social targets. Each target is
 * isolated: a failure is logged and recorded, the others still run. Dry run
 * needs no credentials and makes no network call. Returns the failed targets.
 */
export async function runSocial(
  targets: readonly SocialTarget[],
  type: SocialType,
  version: string,
  notes: string | null,
  dryRun: boolean,
  env: Env = process.env,
): Promise<SocialTarget[]> {
  const failed: SocialTarget[] = [];
  for (const target of targets) {
    try {
      const mastodonText = target === "mastodon" ? buildMastodonText(type, version, notes) : "";
      const blueskyPost = target === "bluesky" ? buildBlueskyPost(type, version, notes) : null;
      if (dryRun) {
        const missing = missingEnv(target, env);
        if (missing.length > 0) {
          log(`note [${target}]: a real run would fail, missing: ${missing.join(", ")}`);
        }
        if (target === "mastodon") previewMastodon(mastodonText);
        else previewBluesky(blueskyPost!);
        continue;
      }
      const missing = missingEnv(target, env);
      if (missing.length > 0) {
        throw new Error(`missing environment variable(s): ${missing.join(", ")}`);
      }
      const where =
        target === "mastodon"
          ? await postMastodon(mastodonText, env, version)
          : await postBluesky(blueskyPost!, env);
      log(`posted to ${target}: ${where}`);
    } catch (err) {
      log(`ERROR [${target}]: ${err instanceof Error ? err.message : String(err)}`);
      failed.push(target);
    }
  }
  return failed;
}
