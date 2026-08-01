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
    // never the value.
    expect(() => parseEnv({ DISCORD_BOT_TOKEN: "t", DISCORD_GUILD_ID: "" })).toThrow(
      expect.not.stringContaining("t"),
    );
  });
});
