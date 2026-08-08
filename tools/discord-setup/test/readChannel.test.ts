import { describe, it, expect } from "vitest";
import { ChannelType, type GuildBasedChannel } from "discord.js";
import {
  formatBytes,
  formatMessage,
  formatChannelLine,
  parseLimit,
  typeName,
} from "../src/readChannel.js";

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

  it("treats a missing attachment list like an empty one", () => {
    // Keeps the three-argument call shape valid for callers that have no
    // attachment data to pass.
    expect(formatMessage("elric", "2026-08-01T10:00:00.000Z", "hi", undefined)).toBe(
      "[2026-08-01T10:00:00.000Z] elric: hi",
    );
  });
});

describe("formatMessage attachments", () => {
  const iso = "2026-08-05T17:39:16.611Z";

  it("lists an attachment on its own line after the body", () => {
    // The real case this exists for: a support-export ZIP dropped in
    // #bug-report. Before this, the file was invisible from the CLI and the
    // message read as if the user had sent nothing usable.
    const line = formatMessage("shedman214", iso, "Here is my logs.", [
      { name: "support-export.zip", size: 1536, url: "https://cdn.discordapp.com/a/support.zip" },
    ]);
    expect(line).toBe(
      `[${iso}] shedman214: Here is my logs.\n` +
        "  attachment: support-export.zip (1.5 KB) https://cdn.discordapp.com/a/support.zip",
    );
  });

  it("lists every attachment when a message carries several", () => {
    const line = formatMessage("elric", iso, "screenshots", [
      { name: "one.png", size: 100, url: "https://cdn.discordapp.com/one.png" },
      { name: "two.png", size: 200, url: "https://cdn.discordapp.com/two.png" },
    ]);
    expect(line.split("\n")).toEqual([
      `[${iso}] elric: screenshots`,
      "  attachment: one.png (100 B) https://cdn.discordapp.com/one.png",
      "  attachment: two.png (200 B) https://cdn.discordapp.com/two.png",
    ]);
  });

  it("reports an attachment-only message as such, not as missing text content", () => {
    // Discord gates `content` and `attachments` behind the same privileged
    // MessageContent intent, so a visible attachment proves the intent is on.
    // Reusing the "(no text content)" placeholder here would point at a
    // permission problem that does not exist.
    const line = formatMessage("elric", iso, "", [
      { name: "shot.png", size: 2048, url: "https://cdn.discordapp.com/shot.png" },
    ]);
    expect(line).toContain("(attachment only)");
    expect(line).not.toContain("(no text content)");
    expect(line).toContain("attachment: shot.png (2 KB) https://cdn.discordapp.com/shot.png");
  });

  it("still reports missing text content when there is no attachment either", () => {
    expect(formatMessage("elric", iso, "", [])).toContain("(no text content)");
  });
});

describe("formatBytes", () => {
  it("renders bytes below one kilobyte with the byte unit", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
  });

  it("renders a fractional kilobyte value with one decimal", () => {
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("drops a trailing zero decimal", () => {
    expect(formatBytes(2048)).toBe("2 KB");
  });

  it("scales into megabytes and gigabytes", () => {
    expect(formatBytes(1024 * 1024)).toBe("1 MB");
    expect(formatBytes(1024 * 1024 * 1024)).toBe("1 GB");
  });

  it("keeps oversized values in the largest unit rather than running off the scale", () => {
    expect(formatBytes(5 * 1024 * 1024 * 1024 * 1024)).toBe("5120 GB");
  });

  it("does not render a negative or non-finite size as a unit value", () => {
    // Defensive: `size` comes from the Discord API, so it is external input.
    expect(formatBytes(-1)).toBe("unknown size");
    expect(formatBytes(Number.NaN)).toBe("unknown size");
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
