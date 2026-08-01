import { describe, it, expect } from "vitest";
import { ChannelType, type GuildBasedChannel } from "discord.js";
import { formatMessage, formatChannelLine, parseLimit, typeName } from "../src/readChannel.js";

/** A minimal stand-in for a discord.js channel — `typeName` only reads `.type`. */
function fakeChannel(type: ChannelType): GuildBasedChannel {
  return { type } as unknown as GuildBasedChannel;
}

describe("formatMessage", () => {
  it("renders author, timestamp and body on one line", () => {
    expect(formatMessage("elric", "2026-08-01T10:00:00.000Z", "subs are missing")).toBe(
      "[2026-08-01T10:00:00.000Z] elric: subs are missing",
    );
  });

  it("marks empty content instead of rendering a blank line", () => {
    // An empty body means the MessageContent intent is off. Rendering nothing
    // would look like an empty server rather than a missing permission.
    expect(formatMessage("elric", "2026-08-01T10:00:00.000Z", "")).toContain("(no text content)");
  });

  it("marks whitespace-only content the same way", () => {
    expect(formatMessage("elric", "2026-08-01T10:00:00.000Z", "   \n ")).toContain(
      "(no text content)",
    );
  });
});

describe("typeName", () => {
  it("names a text channel", () => {
    expect(typeName(fakeChannel(ChannelType.GuildText))).toBe("text");
  });

  it("names a forum channel", () => {
    expect(typeName(fakeChannel(ChannelType.GuildForum))).toBe("forum");
  });

  it("names a public thread — forum posts render this way, e.g. #bug-report threads", () => {
    expect(typeName(fakeChannel(ChannelType.PublicThread))).toBe("thread");
  });

  it("names a private thread", () => {
    expect(typeName(fakeChannel(ChannelType.PrivateThread))).toBe("thread");
  });

  it("names an announcement thread", () => {
    expect(typeName(fakeChannel(ChannelType.AnnouncementThread))).toBe("thread");
  });

  it("falls back to a numbered label for an unhandled type", () => {
    expect(typeName(fakeChannel(ChannelType.GuildStageVoice))).toBe(
      `type-${ChannelType.GuildStageVoice}`,
    );
  });
});

describe("formatChannelLine", () => {
  it("renders name, type and id", () => {
    expect(formatChannelLine("bug-report", "forum", "123")).toBe("  #bug-report  [forum]  id 123");
  });
});

describe("parseLimit", () => {
  it("defaults to 20 when the argument is missing", () => {
    expect(parseLimit(undefined)).toBe(20);
  });

  it("defaults to 20 for non-numeric input", () => {
    expect(parseLimit("abc")).toBe(20);
  });

  it("defaults to 20 for zero", () => {
    expect(parseLimit("0")).toBe(20);
  });

  it("defaults to 20 for negative numbers", () => {
    expect(parseLimit("-5")).toBe(20);
  });

  it("accepts the minimum value 1", () => {
    expect(parseLimit("1")).toBe(1);
  });

  it("accepts the default value 20", () => {
    expect(parseLimit("20")).toBe(20);
  });

  it("accepts the maximum value 100", () => {
    expect(parseLimit("100")).toBe(100);
  });

  it("clamps values above 100 to 100 instead of falling back to the default", () => {
    expect(parseLimit("500")).toBe(100);
  });

  it("defaults to 20 for non-integer values", () => {
    expect(parseLimit("12.5")).toBe(20);
  });
});
