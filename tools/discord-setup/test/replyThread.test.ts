import { describe, it, expect, vi } from "vitest";
import { resolveThread, resolveTextChannel, resolveReplyTarget } from "../src/replyThread.js";

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

  it("returns null when a substring matches several threads, and logs both candidates", () => {
    // "Subtitles" hits 111 and 333. Guessing here posts a public reply into the
    // wrong conversation, which is not undoable. Spying on console.log both
    // keeps test output pristine and proves the candidate list is actually
    // printed — a regression that dropped the log() calls would otherwise
    // still pass on the `toBeNull()` assertion alone.
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(resolveThread(THREADS, "Subtitles")).toBeNull();
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('"Subtitles" is ambiguous'));
      expect(logSpy).toHaveBeenCalledWith(
        expect.stringContaining('"Subtitles not downloading for anime"  (id 111)'),
      );
      expect(logSpy).toHaveBeenCalledWith(
        expect.stringContaining('"Subtitles out of sync"  (id 333)'),
      );
    } finally {
      logSpy.mockRestore();
    }
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

describe("resolveReplyTarget", () => {
  it("an exact channel name beats a substring-matching thread", () => {
    // A text channel #support exists; a forum thread's TITLE also happens to
    // contain "support" as a substring. The exact channel match must win —
    // picking the thread here silently misposts into an unrelated public
    // conversation, which is exactly what this task's rails exist to prevent.
    const threads = [{ id: "t1", name: "Support ticket: xyz issue" }];
    const channels = [{ id: "c1", name: "support" }];
    expect(resolveReplyTarget(threads, channels, "support")?.id).toBe("c1");
  });

  it("an exact thread id still wins", () => {
    const threads = [{ id: "111", name: "unrelated title" }];
    const channels = [{ id: "c1", name: "other-channel" }];
    expect(resolveReplyTarget(threads, channels, "111")?.id).toBe("111");
  });

  it("aborts as ambiguous when an exact thread name and an exact channel name collide, and logs both candidates", () => {
    const threads = [{ id: "t1", name: "support" }];
    const channels = [{ id: "c1", name: "support" }];
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(resolveReplyTarget(threads, channels, "support")).toBeNull();
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('"support" is ambiguous'));
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining("(thread, id t1)"));
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining("(channel, id c1)"));
    } finally {
      logSpy.mockRestore();
    }
  });

  it("falls back to a unique thread-title substring when there is no exact match", () => {
    const threads = [{ id: "t1", name: "Support ticket: xyz issue" }];
    const channels = [{ id: "c1", name: "general" }];
    expect(resolveReplyTarget(threads, channels, "ticket")?.id).toBe("t1");
  });

  it("aborts when there is no exact match and the substring fallback is itself ambiguous", () => {
    const threads = [
      { id: "t1", name: "Subtitles not downloading for anime" },
      { id: "t2", name: "Subtitles out of sync" },
    ];
    const channels = [{ id: "c1", name: "general" }];
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(resolveReplyTarget(threads, channels, "Subtitles")).toBeNull();
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('"Subtitles" is ambiguous'));
    } finally {
      logSpy.mockRestore();
    }
  });
});
