import { describe, it, expect } from "vitest";
import { formatMessage, formatChannelLine } from "../src/readChannel.js";

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

describe("formatChannelLine", () => {
  it("renders name, type and id", () => {
    expect(formatChannelLine("bug-report", "forum", "123")).toBe("  #bug-report  [forum]  id 123");
  });
});
