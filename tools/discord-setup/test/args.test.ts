import { describe, it, expect } from "vitest";
import { parseArgs } from "../src/args.js";

describe("parseArgs", () => {
  it("takes positional arguments when no flags are present", () => {
    const { positional } = parseArgs(["general", "hello", "world"], ["--file"], ["--dry-run"]);
    expect(positional).toEqual(["general", "hello", "world"]);
  });

  it("removes a trailing boolean flag from the positional list", () => {
    const { positional } = parseArgs(["general", "hello", "--dry-run"], [], ["--dry-run"]);
    expect(positional).toEqual(["general", "hello"]);
  });

  it("removes a LEADING boolean flag from the positional list — flag position does not matter", () => {
    // This is the exact repro from finding 3: `reply -- --dry-run general "msg"`
    // used to read the literal string "--dry-run" as the target because
    // targetQuery came from a fixed argv index.
    const { positional } = parseArgs(["--dry-run", "general", "hello"], [], ["--dry-run"]);
    expect(positional).toEqual(["general", "hello"]);
  });

  it("removes a boolean flag from the middle of the arguments", () => {
    const { positional } = parseArgs(["general", "--dry-run", "hello"], [], ["--dry-run"]);
    expect(positional).toEqual(["general", "hello"]);
  });

  it("captures a value flag's following argument and removes both from positional", () => {
    const { positional, values } = parseArgs(
      ["general", "--file", "/tmp/msg.txt"],
      ["--file"],
      ["--dry-run"],
    );
    expect(positional).toEqual(["general"]);
    expect(values["--file"]).toBe("/tmp/msg.txt");
  });

  it("captures a value flag placed before the positional arguments", () => {
    const { positional, values } = parseArgs(
      ["--file", "/tmp/msg.txt", "general"],
      ["--file"],
      ["--dry-run"],
    );
    expect(positional).toEqual(["general"]);
    expect(values["--file"]).toBe("/tmp/msg.txt");
  });

  it("handles a value flag and a boolean flag together, in any order", () => {
    const { positional, values } = parseArgs(
      ["--dry-run", "beta", "--notes-file", "/tmp/notes.txt"],
      ["--notes-file", "--notes"],
      ["--dry-run"],
    );
    expect(positional).toEqual(["beta"]);
    expect(values["--notes-file"]).toBe("/tmp/notes.txt");
  });

  it("leaves values empty for flags that were never passed", () => {
    const { values } = parseArgs(["general", "hello"], ["--file"], ["--dry-run"]);
    expect(values["--file"]).toBeUndefined();
  });

  it("pins the intended behaviour when a value flag is the last token: undefined, no throw", () => {
    // A value flag with nothing after it (`reply general --file`) has no
    // path to read. This degrades gracefully to `values["--file"] ===
    // undefined` rather than throwing — same as the old indexOf-based code,
    // not a regression introduced by this rewrite. Pinned here so a future
    // change to this file has to make that choice deliberately rather than
    // stumble into throwing (or silently reading past the array) unnoticed.
    const { positional, values } = parseArgs(["general", "--file"], ["--file"], ["--dry-run"]);
    expect(positional).toEqual(["general"]);
    expect(values["--file"]).toBeUndefined();
  });
});
