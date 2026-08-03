import { describe, it, expect, afterAll } from "vitest";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { isKnownCommand, readFlagFile } from "../src/index.js";

describe("isKnownCommand", () => {
  it("accepts each known command", () => {
    expect(isKnownCommand("read")).toBe(true);
    expect(isKnownCommand("reply")).toBe(true);
    expect(isKnownCommand("announce")).toBe(true);
  });

  it("rejects an unknown command", () => {
    expect(isKnownCommand("bogus-command")).toBe(false);
  });

  it("rejects undefined — no command given at all", () => {
    expect(isKnownCommand(undefined)).toBe(false);
  });
});

describe("readFlagFile", () => {
  const dir = mkdtempSync(join(tmpdir(), "sublarr-discord-test-"));

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("returns the file contents on a readable path", () => {
    const path = join(dir, "notes.txt");
    writeFileSync(path, "release notes\n", "utf8");
    expect(readFlagFile("--notes-file", path)).toBe("release notes\n");
  });

  it("throws an error naming the flag and the path for an unreadable path", () => {
    const path = join(dir, "does-not-exist.txt");
    expect(() => readFlagFile("--file", path)).toThrow(/--file/);
    expect(() => readFlagFile("--file", path)).toThrow(path);
  });

  it("names the specific flag passed, not a generic message", () => {
    const path = join(dir, "also-missing.txt");
    expect(() => readFlagFile("--notes-file", path)).toThrow(/--notes-file/);
  });
});
