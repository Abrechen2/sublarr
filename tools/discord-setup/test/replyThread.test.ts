import { describe, it, expect } from "vitest";
import { resolveThread, resolveTextChannel } from "../src/replyThread.js";

const THREADS = [
  { id: "111", name: "Subtitles not downloading for anime" },
  { id: "222", name: "Feature: bulk re-scan" },
  { id: "333", name: "Subtitles out of sync" },
];

describe("resolveThread", () => {
  it("matches an exact id", () => {
    expect(resolveThread(THREADS, "222")?.id).toBe("222");
  });

  it("matches a unique case-insensitive title substring", () => {
    expect(resolveThread(THREADS, "bulk re-scan")?.id).toBe("222");
    expect(resolveThread(THREADS, "BULK")?.id).toBe("222");
  });

  it("returns null when a substring matches several threads", () => {
    // "Subtitles" hits 111 and 333. Guessing here posts a public reply into the
    // wrong conversation, which is not undoable.
    expect(resolveThread(THREADS, "Subtitles")).toBeNull();
  });

  it("returns null when nothing matches", () => {
    expect(resolveThread(THREADS, "nonexistent")).toBeNull();
  });

  it("prefers an id match over a substring match", () => {
    const threads = [
      { id: "111", name: "about 222 really" },
      { id: "222", name: "the real one" },
    ];
    expect(resolveThread(threads, "222")?.id).toBe("222");
  });
});

describe("resolveTextChannel", () => {
  const CHANNELS = [
    { id: "a1", name: "general" },
    { id: "a2", name: "general-dev" },
    { id: "a3", name: "announcements" },
  ];

  it("matches an exact name", () => {
    expect(resolveTextChannel(CHANNELS, "general")?.id).toBe("a1");
  });

  it("tolerates a leading hash", () => {
    expect(resolveTextChannel(CHANNELS, "#general")?.id).toBe("a1");
  });

  it("is case-insensitive on the exact name", () => {
    expect(resolveTextChannel(CHANNELS, "General")?.id).toBe("a1");
  });

  it("never matches a substring", () => {
    // Substring matching would resolve "general" to "#general-dev" depending on
    // iteration order. Exact only.
    expect(resolveTextChannel(CHANNELS, "gener")).toBeNull();
  });

  it("matches an id", () => {
    expect(resolveTextChannel(CHANNELS, "a3")?.id).toBe("a3");
  });
});
