import { describe, it, expect } from "vitest";
import { stripPrerelease, extractChangelogEntry } from "../src/changelog.js";

const SAMPLE = `# Changelog

All notable changes to Sublarr are documented in this file.

## [1.10.0] - 2026-08-01

### Added
- Waveform editor speech detection.
- Custom regex scoring rules.

## [1.9.4] - 2026-07-18

### Fixed
- Health endpoint no longer stalls.
`;

describe("stripPrerelease", () => {
  it("strips an rc suffix", () => {
    expect(stripPrerelease("1.10.0-rc.2")).toBe("1.10.0");
  });

  it("strips a beta suffix", () => {
    expect(stripPrerelease("1.10.0-beta")).toBe("1.10.0");
  });

  it("leaves a final version alone", () => {
    expect(stripPrerelease("1.10.0")).toBe("1.10.0");
  });
});

describe("extractChangelogEntry", () => {
  it("returns the body of the matching entry", () => {
    const entry = extractChangelogEntry(SAMPLE, "1.10.0");
    expect(entry).toContain("Waveform editor speech detection");
    expect(entry).toContain("Custom regex scoring rules");
  });

  it("stops at the next version heading", () => {
    const entry = extractChangelogEntry(SAMPLE, "1.10.0");
    expect(entry).not.toContain("Health endpoint");
  });

  it("maps an rc version onto its base entry", () => {
    expect(extractChangelogEntry(SAMPLE, "1.10.0-rc.2")).toContain("Waveform editor");
  });

  it("returns null for a version with no entry", () => {
    expect(extractChangelogEntry(SAMPLE, "9.9.9")).toBeNull();
  });

  it("does not let a truncated version match a longer heading via word boundary", () => {
    // The word boundary \b after the version is load-bearing. Without it, "1.1" would
    // match the heading "## [1.10.0]" because the regex would find "1.1" and continue.
    // The \b requires a word boundary after the version digits, preventing "1.1" from
    // matching when followed by another digit "0" in "1.10.0".
    expect(extractChangelogEntry(SAMPLE, "1.1")).toBeNull();
  });

  it("correctly escapes dots in version strings", () => {
    // Dot-escaping ensures "1.1.0" (with literal dots) does not accidentally match
    // "1.10.0" via a literal dot in the version string. Separate concern from word boundary.
    expect(extractChangelogEntry(SAMPLE, "1.1.0")).toBeNull();
  });

  it("handles a heading without brackets", () => {
    expect(extractChangelogEntry("## 2.0.0 - 2026-01-01\n\n- Thing\n", "2.0.0")).toContain("Thing");
  });
});
