import { describe, it, expect } from "vitest";
import { editRefusal } from "../src/editMessage.js";
import { isKnownCommand } from "../src/index.js";

const BOT = "900";

describe("editRefusal", () => {
  it("allows the bot's own message", () => {
    expect(editRefusal({ authorId: BOT, content: "old" }, BOT, "new")).toBeNull();
  });

  it("refuses somebody else's message — the bot must never rewrite a user's words", () => {
    expect(editRefusal({ authorId: "123", content: "old" }, BOT, "new")).toMatch(/not posted by this bot/);
  });

  it("refuses an edit that changes nothing", () => {
    expect(editRefusal({ authorId: BOT, content: "same" }, BOT, "same")).toMatch(/identical/);
  });

  it("refuses a message over Discord's 2000-character limit", () => {
    expect(editRefusal({ authorId: BOT, content: "old" }, BOT, "x".repeat(2001))).toMatch(/2000/);
  });
});

describe("isKnownCommand", () => {
  it("knows edit", () => {
    expect(isKnownCommand("edit")).toBe(true);
  });
});
