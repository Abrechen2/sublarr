import { describe, it, expect } from "vitest";
import { buildAnnounceEmbed, channelForType, readRepoVersion } from "../src/announce.js";
import { ANNOUNCE_CHANNELS } from "../src/channels.js";

describe("channelForType", () => {
  it("routes each lane to its configured channel", () => {
    expect(channelForType("beta")).toBe(ANNOUNCE_CHANNELS.beta);
    expect(channelForType("rc")).toBe(ANNOUNCE_CHANNELS.rc);
    expect(channelForType("release")).toBe(ANNOUNCE_CHANNELS.release);
  });

  // Each lane has its own channel since #release-candidate was created
  // 2026-08-01. Pinned separately so a future edit that accidentally
  // collapses two lanes onto the same channel is caught here, distinct from
  // the "routes each lane to its configured channel" check above.
  it("resolves the three lanes to three distinct channels", () => {
    const targets = (["beta", "rc", "release"] as const).map(channelForType);
    expect(new Set(targets).size).toBe(3);
  });
});

describe("buildAnnounceEmbed", () => {
  it("builds a release embed with the Sublarr teal and the version in the title", () => {
    const data = buildAnnounceEmbed("release", "1.10.0", "- Thing").toJSON();
    expect(data.title).toContain("1.10.0");
    expect(data.color).toBe(0x1db8d4);
    expect(data.description).toContain("Thing");
  });

  it("links the vX.Y.Z GitHub tag", () => {
    const data = buildAnnounceEmbed("release", "1.10.0", null).toJSON();
    expect(data.description).toContain(
      "https://github.com/abrechen2/sublarr/releases/tag/v1.10.0",
    );
  });

  it("keeps the full pre-release version in the tag link", () => {
    // The changelog LOOKUP strips -rc.N; the release TAG does not.
    const data = buildAnnounceEmbed("rc", "1.10.0-rc.2", null).toJSON();
    expect(data.description).toContain("releases/tag/v1.10.0-rc.2");
  });

  it("distinguishes the three lanes by colour", () => {
    const colors = (["beta", "rc", "release"] as const).map(
      (t) => buildAnnounceEmbed(t, "1.0.0", null).toJSON().color,
    );
    expect(new Set(colors).size).toBe(3);
  });

  it("falls back to a notice when notes are null", () => {
    const data = buildAnnounceEmbed("release", "1.10.0", null).toJSON();
    expect(data.description).toContain("See the changelog");
  });

  it("falls back when notes are whitespace only", () => {
    const data = buildAnnounceEmbed("release", "1.10.0", "   \n  ").toJSON();
    expect(data.description).toContain("See the changelog");
  });

  it("truncates notes past the embed limit", () => {
    const data = buildAnnounceEmbed("release", "1.10.0", "x".repeat(5000)).toJSON();
    expect(data.description!.length).toBeLessThan(4096);
    expect(data.description).toContain("…");
  });

  it("stamps a findable footer marker", () => {
    const data = buildAnnounceEmbed("release", "1.10.0", null).toJSON();
    expect(data.footer?.text).toBe("sublarr-release-1.10.0");
  });
});

describe("readRepoVersion", () => {
  it("reads the real backend/VERSION", () => {
    expect(readRepoVersion()).toMatch(/^\d+\.\d+\.\d+/);
  });
});
