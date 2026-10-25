import { describe, it, expect } from "vitest";
import {
  buildBlueskyPost,
  buildFacets,
  buildMastodonText,
  charCount,
  extractHighlights,
  graphemeCount,
  releaseUrl,
  truncateAtWord,
} from "../src/socialText.js";
import { missingEnv, parseTargets, runSocial } from "../src/social.js";

const NOTES = `Intro line.

**Security (1.17.2)**
- **Apprise updated to 1.13.1.** Older versions followed redirects.
- **setuptools updated** past two advisories.
- **follow-redirects updated to 1.16.1** in the frontend.

**Fixed**
- **Path mapping matches whole folders.** Detail detail detail.
- **Fifth bullet is dropped.** x
`;

const LONG = Array.from(
  { length: 8 },
  (_, i) => `- Überlänge Feature ${i} — ${"wort ".repeat(60)}`,
).join("\n");

describe("extractHighlights", () => {
  it("uses the bold lead of bullets, max 4, markdown stripped", () => {
    const h = extractHighlights(NOTES);
    expect(h).toHaveLength(4);
    expect(h[0]).toBe("Apprise updated to 1.13.1");
    expect(h[3]).toBe("Path mapping matches whole folders");
  });
  it("returns [] for null notes", () => {
    expect(extractHighlights(null)).toEqual([]);
  });
});

describe("truncateAtWord", () => {
  it("never cuts mid-word", () => {
    const out = truncateAtWord("alpha beta gamma delta", 14);
    expect(out).toBe("alpha beta…");
  });
  it("returns the input when it fits", () => {
    expect(truncateAtWord("short", 10)).toBe("short");
  });
});

describe("buildMastodonText", () => {
  it("stays within 500 chars and keeps the full URL and hashtags", () => {
    for (const notes of [NOTES, LONG, null]) {
      const t = buildMastodonText("release", "1.17.2", notes);
      expect(charCount(t)).toBeLessThanOrEqual(500);
      expect(t).toContain(releaseUrl("1.17.2"));
      expect(t).toContain("#anime");
      expect(t.startsWith("Sublarr 1.17.2 released")).toBe(true);
    }
  });
  it("includes 2-4 highlight bullets for normal notes", () => {
    const t = buildMastodonText("release", "1.17.2", NOTES);
    const bullets = t.split("\n").filter((l) => l.startsWith("• "));
    expect(bullets.length).toBeGreaterThanOrEqual(2);
    expect(bullets.length).toBeLessThanOrEqual(4);
  });
  it("truncated bullets end on a whole word with an ellipsis", () => {
    const t = buildMastodonText("release", "1.17.2", LONG);
    const last = t.split("\n").filter((l) => l.startsWith("• ")).pop()!;
    expect(last.endsWith("…")).toBe(true);
    expect(last.slice(0, -1).split(" ").pop()).toMatch(/^(wort|—|\d|Feature|Überlänge)$/);
  });
});

describe("buildBlueskyPost", () => {
  it("stays within 300 graphemes", () => {
    for (const notes of [NOTES, LONG, null]) {
      const p = buildBlueskyPost("release", "1.17.2", notes);
      expect(graphemeCount(p.text)).toBeLessThanOrEqual(300);
      expect(p.text).toContain(releaseUrl("1.17.2"));
    }
  });
  it("link facet has correct UTF-8 byte offsets after non-ASCII text", () => {
    const notes = "- **Größe — Übersicht fertig**\n- **Zweiter Punkt**";
    const p = buildBlueskyPost("release", "1.17.2", notes);
    const url = releaseUrl("1.17.2");
    const bytes = new TextEncoder().encode(p.text);
    const link = p.facets.find((f) => f.features[0].$type.endsWith("#link"))!;
    const slice = new TextDecoder().decode(bytes.slice(link.index.byteStart, link.index.byteEnd));
    expect(slice).toBe(url);
    // Proves the test is meaningful: char index and byte offset differ.
    expect(link.index.byteStart).toBeGreaterThan(p.text.indexOf(url));
  });
  it("tag facets point at the tag bytes", () => {
    const p = buildBlueskyPost("release", "1.17.2", "- **Über — alles**");
    const bytes = new TextEncoder().encode(p.text);
    for (const f of p.facets.filter((x) => x.features[0].$type.endsWith("#tag"))) {
      const s = new TextDecoder().decode(bytes.slice(f.index.byteStart, f.index.byteEnd));
      expect(s).toBe(`#${(f.features[0] as { tag: string }).tag}`);
    }
  });
  it("adds an external link card with title and description, no thumb", () => {
    const p = buildBlueskyPost("release", "1.17.2", NOTES);
    expect(p.embed.$type).toBe("app.bsky.embed.external");
    expect(p.embed.external.uri).toBe(releaseUrl("1.17.2"));
    expect(p.embed.external.title).toBe("Sublarr 1.17.2 released");
    expect(p.embed.external.description.length).toBeGreaterThan(0);
    expect("thumb" in p.embed.external).toBe(false);
  });
});

describe("buildFacets", () => {
  it("handles an emoji (4-byte) before the URL", () => {
    const url = "https://example.com/x";
    const text = `🚀 ä ${url}`;
    const [f] = buildFacets(text, url, []);
    const out = new TextDecoder().decode(new TextEncoder().encode(text).slice(f.index.byteStart, f.index.byteEnd));
    expect(out).toBe(url);
  });
});

describe("targets and env", () => {
  it("defaults to discord only and rejects unknown targets", () => {
    expect(parseTargets(undefined)).toEqual(["discord"]);
    expect(parseTargets("discord, Mastodon,bluesky")).toEqual(["discord", "mastodon", "bluesky"]);
    expect(() => parseTargets("twitter")).toThrow(/Unknown/);
  });
  it("names missing variables without values", () => {
    expect(missingEnv("mastodon", { MASTODON_INSTANCE: "https://x" })).toEqual([
      "MASTODON_ACCESS_TOKEN",
    ]);
    expect(missingEnv("bluesky", {})).toEqual(["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"]);
  });
  it("fails one target but still processes the next; dry run needs no env", async () => {
    const failed = await runSocial(["mastodon", "bluesky"], "release", "1.17.2", NOTES, false, {});
    expect(failed).toEqual(["mastodon", "bluesky"]);
    const dry = await runSocial(["mastodon", "bluesky"], "release", "1.17.2", NOTES, true, {});
    expect(dry).toEqual([]);
  });
});
