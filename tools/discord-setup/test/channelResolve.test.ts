import { describe, it, expect, vi } from "vitest";
import { ChannelType } from "discord.js";
import { isMessageCapable, resolveChannelByExactName } from "../src/channelResolve.js";

const typeName = (c: { type: ChannelType }): string => {
  switch (c.type) {
    case ChannelType.GuildText:
      return "text";
    case ChannelType.GuildVoice:
      return "voice";
    case ChannelType.GuildForum:
      return "forum";
    default:
      return `type-${c.type}`;
  }
};

describe("isMessageCapable", () => {
  it("accepts text, announcement, forum and every thread type", () => {
    expect(isMessageCapable({ type: ChannelType.GuildText })).toBe(true);
    expect(isMessageCapable({ type: ChannelType.GuildAnnouncement })).toBe(true);
    expect(isMessageCapable({ type: ChannelType.GuildForum })).toBe(true);
    expect(isMessageCapable({ type: ChannelType.PublicThread })).toBe(true);
    expect(isMessageCapable({ type: ChannelType.PrivateThread })).toBe(true);
    expect(isMessageCapable({ type: ChannelType.AnnouncementThread })).toBe(true);
  });

  it("rejects voice and category channels", () => {
    // Voice channels satisfy discord.js's isTextBased() (every voice channel
    // has a text chat) but do not hold the conversations `read`/`announce`
    // care about — that gap is exactly what let a voice channel win the
    // live collision below.
    expect(isMessageCapable({ type: ChannelType.GuildVoice })).toBe(false);
    expect(isMessageCapable({ type: ChannelType.GuildCategory })).toBe(false);
  });
});

describe("resolveChannelByExactName", () => {
  // Reproduces the live collision found in the guild on 2026-08-01: a type-0
  // text #general (5 messages, the community's main channel) and a type-2
  // voice #General (0 messages). The voice entry is listed FIRST here,
  // matching the real `guild.channels.cache` iteration order that made the
  // pre-fix `all.find((c) => c.name.toLowerCase() === needle)` in
  // readChannel.ts pick it — `find` returns the first match, so this
  // ordering is exactly what made the bug live rather than theoretical.
  const GENERAL_COLLISION = [
    { id: "voice-1", name: "General", type: ChannelType.GuildVoice },
    { id: "text-1", name: "general", type: ChannelType.GuildText },
  ];

  it("picks the text channel over a same-name voice channel", () => {
    const resolved = resolveChannelByExactName(GENERAL_COLLISION, "general", typeName);
    expect(resolved?.id).toBe("text-1");
  });

  it("matches case-insensitively and tolerates a leading hash", () => {
    expect(resolveChannelByExactName(GENERAL_COLLISION, "#General", typeName)?.id).toBe("text-1");
  });

  it("matches an id", () => {
    expect(resolveChannelByExactName(GENERAL_COLLISION, "text-1", typeName)?.id).toBe("text-1");
  });

  it("returns null when nothing matches", () => {
    expect(resolveChannelByExactName(GENERAL_COLLISION, "nonexistent", typeName)).toBeNull();
  });

  it("never matches a substring", () => {
    expect(resolveChannelByExactName(GENERAL_COLLISION, "gener", typeName)).toBeNull();
  });

  it("aborts and logs every candidate when two message-capable channels collide by name", () => {
    const channels = [
      { id: "f1", name: "support", type: ChannelType.GuildForum },
      { id: "t1", name: "support", type: ChannelType.GuildText },
    ];
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(resolveChannelByExactName(channels, "support", typeName)).toBeNull();
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('"support" is ambiguous'));
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining("(forum, id f1)"));
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining("(text, id t1)"));
    } finally {
      logSpy.mockRestore();
    }
  });
});
