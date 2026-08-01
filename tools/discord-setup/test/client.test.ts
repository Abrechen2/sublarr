import { describe, it, expect } from "vitest";
import { parseEnv } from "../src/client.js";

describe("parseEnv", () => {
  it("returns both values when present", () => {
    expect(parseEnv({ DISCORD_BOT_TOKEN: "t", DISCORD_GUILD_ID: "g" })).toEqual({
      token: "t",
      guildId: "g",
    });
  });

  it("throws naming the missing token", () => {
    expect(() => parseEnv({ DISCORD_GUILD_ID: "g" })).toThrow(/DISCORD_BOT_TOKEN/);
  });

  it("throws naming the missing guild id", () => {
    expect(() => parseEnv({ DISCORD_BOT_TOKEN: "t" })).toThrow(/DISCORD_GUILD_ID/);
  });

  it("treats an empty string as missing", () => {
    expect(() => parseEnv({ DISCORD_BOT_TOKEN: "", DISCORD_GUILD_ID: "g" })).toThrow(
      /DISCORD_BOT_TOKEN/,
    );
  });

  it("does not put the token value in the error message", () => {
    // A thrown error can end up in a log or a transcript. It may name the key,
    // never the value. Uses a distinctive value (not the single-char "t" used
    // elsewhere in this file) because a single common letter is a substring of
    // ordinary English words in the error copy ("to", "it"), which would make
    // this assertion pass vacuously regardless of what parseEnv actually does.
    const secretTokenValue = "sk-should-never-leak-into-message";
    try {
      parseEnv({ DISCORD_BOT_TOKEN: secretTokenValue, DISCORD_GUILD_ID: "" });
      expect.fail("expected parseEnv to throw");
    } catch (err) {
      expect((err as Error).message).not.toContain(secretTokenValue);
    }
  });
});
