// Pure text builders for the Mastodon and Bluesky announcements. No I/O, so
// the length limits and the UTF-8 byte offsets are unit-testable.

export type SocialType = "beta" | "rc" | "release";

export const MASTODON_LIMIT = 500; // characters
export const BLUESKY_LIMIT = 300; // graphemes
export const MAX_HIGHLIGHTS = 4;
const MIN_TRUNCATED = 15;

const REPO_URL = "https://github.com/abrechen2/sublarr";

export const MASTODON_HASHTAGS = [
  "#selfhosted",
  "#homelab",
  "#subtitles",
  "#sonarr",
  "#radarr",
  "#anime",
] as const;
export const BLUESKY_HASHTAGS = ["#selfhosted", "#homelab", "#subtitles"] as const;

const segmenter = new Intl.Segmenter("en", { granularity: "grapheme" });
const encoder = new TextEncoder();

export function graphemeCount(text: string): number {
  let n = 0;
  for (const _ of segmenter.segment(text)) n++;
  return n;
}

/** Mastodon counts Unicode characters (code points), not UTF-16 units. */
export function charCount(text: string): number {
  return [...text].length;
}

export function releaseUrl(version: string): string {
  return `${REPO_URL}/releases/tag/v${version}`;
}

export function postTitle(type: SocialType, version: string): string {
  if (type === "release") return `Sublarr ${version} released`;
  if (type === "rc") return `Sublarr ${version} release candidate`;
  return `Sublarr ${version} beta`;
}

function stripMarkdown(s: string): string {
  return s
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Pull short highlight lines out of a notes document. Bullets win; a bullet
 * that opens with a bold lead (`- **Lead.** detail`) contributes just the lead.
 * Without bullets, plain non-heading lines are used instead.
 */
export function extractHighlights(notes: string | null, max = MAX_HIGHLIGHTS): string[] {
  if (!notes) return [];
  const lines = notes.split(/\r?\n/);
  const bullets = lines
    .map((l) => /^\s*[-*+]\s+(.*\S)\s*$/.exec(l)?.[1])
    .filter((l): l is string => l !== undefined);
  const raw = bullets.length > 0 ? bullets : lines.filter((l) => l.trim() && !/^\s*#/.test(l));
  const out: string[] = [];
  for (const item of raw) {
    const lead = /^\*\*(.+?)\*\*/.exec(item)?.[1];
    const text = stripMarkdown(lead ?? item).replace(/[.:]+$/, "");
    if (text.length > 0) out.push(text);
    if (out.length >= max) break;
  }
  return out;
}

/**
 * Shorten to at most `max` graphemes, cutting only at a word boundary and
 * appending an ellipsis. Returns "" when not even one whole word fits.
 */
export function truncateAtWord(text: string, max: number): string {
  if (graphemeCount(text) <= max) return text;
  const graphemes = [...segmenter.segment(text)].map((s) => s.segment);
  const head = graphemes.slice(0, Math.max(0, max - 1)).join("");
  // Only cut where the dropped part starts on whitespace, i.e. at a word edge.
  const atBoundary = /\s/.test(graphemes[Math.max(0, max - 1)] ?? "");
  const cut = atBoundary ? head : head.replace(/\s*\S*$/, "");
  const trimmed = cut.replace(/[\s,;:.\-–—(]+$/, "");
  return trimmed.length > 0 ? `${trimmed}…` : "";
}

interface Layout {
  readonly limit: number;
  readonly count: (s: string) => number;
  readonly hashtags: readonly string[];
}

function compose(
  title: string,
  highlights: readonly string[],
  url: string,
  layout: Layout,
): { text: string } {
  const head = `${title}\n\n`;
  const tail = `\n${url}\n\n${layout.hashtags.join(" ")}`;
  let used = layout.count(head) + layout.count(tail);
  const lines: string[] = [];
  for (const h of highlights) {
    const room = layout.limit - used - layout.count("• \n");
    const line = layout.count(h) <= room ? h : truncateAtWord(h, room);
    // A stub like "Fix…" says nothing; skip it rather than post it.
    if (line.length < MIN_TRUNCATED && line !== h) break;
    if (line === "") break;
    lines.push(`• ${line}`);
    used += layout.count(`• ${line}\n`);
    if (line !== h) break;
  }
  // Safety net for emoji clusters: graphemes <= code points, so a line cut by
  // grapheme count can still be over a code-point limit.
  while (lines.length > 0 && layout.count(`${head}${lines.join("\n")}\n${tail}`) > layout.limit) {
    lines.pop();
  }
  const body = lines.length > 0 ? `${head}${lines.join("\n")}\n` : head.trimEnd();
  return { text: `${body}${tail}` };
}

/** Mastodon status text, guaranteed <= 500 characters. */
export function buildMastodonText(
  type: SocialType,
  version: string,
  notes: string | null,
): string {
  const layout: Layout = { limit: MASTODON_LIMIT, count: charCount, hashtags: MASTODON_HASHTAGS };
  return compose(postTitle(type, version), extractHighlights(notes), releaseUrl(version), layout)
    .text;
}

export interface BlueskyFacet {
  readonly index: { readonly byteStart: number; readonly byteEnd: number };
  readonly features: readonly (
    | { readonly $type: "app.bsky.richtext.facet#link"; readonly uri: string }
    | { readonly $type: "app.bsky.richtext.facet#tag"; readonly tag: string }
  )[];
}

export interface BlueskyPost {
  readonly text: string;
  readonly facets: readonly BlueskyFacet[];
  readonly embed: {
    readonly $type: "app.bsky.embed.external";
    readonly external: { readonly uri: string; readonly title: string; readonly description: string };
  };
}

/**
 * Facets for the URL and each hashtag. Offsets are UTF-8 BYTE offsets into
 * `text`, not string indices — anything non-ASCII before the URL (an em dash,
 * an umlaut, an emoji) makes the two differ.
 */
export function buildFacets(text: string, url: string, tags: readonly string[]): BlueskyFacet[] {
  const facets: BlueskyFacet[] = [];
  const byteOffset = (charIndex: number): number =>
    encoder.encode(text.slice(0, charIndex)).length;
  const urlAt = text.indexOf(url);
  if (urlAt >= 0) {
    const start = byteOffset(urlAt);
    facets.push({
      index: { byteStart: start, byteEnd: start + encoder.encode(url).length },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: url }],
    });
  }
  for (const tag of tags) {
    const at = text.lastIndexOf(tag);
    if (at < 0) continue;
    const start = byteOffset(at);
    facets.push({
      index: { byteStart: start, byteEnd: start + encoder.encode(tag).length },
      features: [{ $type: "app.bsky.richtext.facet#tag", tag: tag.slice(1) }],
    });
  }
  return facets;
}

/** Bluesky post body, guaranteed <= 300 graphemes, with link + tag facets and a link card. */
export function buildBlueskyPost(
  type: SocialType,
  version: string,
  notes: string | null,
): BlueskyPost {
  const url = releaseUrl(version);
  const title = postTitle(type, version);
  const highlights = extractHighlights(notes);
  const layout: Layout = { limit: BLUESKY_LIMIT, count: graphemeCount, hashtags: BLUESKY_HASHTAGS };
  const { text } = compose(title, highlights, url, layout);
  const description = truncateAtWord(
    highlights.length > 0 ? highlights.join(" · ") : "See the release notes for details.",
    300,
  );
  return {
    text,
    facets: buildFacets(text, url, BLUESKY_HASHTAGS),
    embed: { $type: "app.bsky.embed.external", external: { uri: url, title, description } },
  };
}
