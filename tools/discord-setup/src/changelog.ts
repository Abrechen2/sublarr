/**
 * Strip a pre-release suffix so an RC or beta version maps to its base
 * changelog entry: "1.10.0-rc.2" -> "1.10.0".
 */
export function stripPrerelease(version: string): string {
  return version.replace(/-.*$/, "");
}

/**
 * Extract the changelog body for a version from a Keep-a-Changelog document.
 * Matches `## [X.Y.Z] …` or `## X.Y.Z …` (brackets optional) for the base
 * version and returns everything up to the next `## ` heading. Returns null
 * when the version has no entry.
 *
 * The `\b` after the escaped version is load-bearing: without it "1.1.0" also
 * matches the "## [1.10.0]" heading and the bot announces the wrong notes.
 */
export function extractChangelogEntry(changelog: string, version: string): string | null {
  const base = stripPrerelease(version);
  const escaped = base.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headingRe = new RegExp(`^##\\s+\\[?${escaped}\\b`);
  const lines = changelog.split(/\r?\n/);

  const start = lines.findIndex((line) => headingRe.test(line));
  if (start === -1) return null;

  const body: string[] = [];
  for (let i = start + 1; i < lines.length; i++) {
    if (/^##\s+/.test(lines[i])) break;
    body.push(lines[i]);
  }

  const text = body.join("\n").trim();
  return text.length > 0 ? text : null;
}
