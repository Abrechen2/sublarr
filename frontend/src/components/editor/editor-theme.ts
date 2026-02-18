/**
 * Sublarr dark and light themes for the CodeMirror subtitle editor.
 *
 * Colors match Sublarr's teal *arr-style design system.
 * Token colors are consistent between ASS and SRT tokenizers:
 * - heading: cyan (section headers)
 * - keyword: purple (Dialogue/Format/Style)
 * - comment: gray italic
 * - number: green (timestamps)
 * - meta: amber (override tags / HTML tags)
 * - propertyName: blue (metadata keys)
 * - escape: orange (\N line breaks)
 * - operator: slate (-->)
 */

import { createTheme } from "@uiw/codemirror-themes";
import { tags as t } from "@lezer/highlight";

/** Dark theme matching Sublarr's default dark mode. */
export const sublarrTheme = createTheme({
  theme: "dark",
  settings: {
    background: "#1a1a2e",
    foreground: "#e2e8f0",
    caret: "#1db8d4",
    selection: "rgba(29, 184, 212, 0.2)",
    selectionMatch: "rgba(29, 184, 212, 0.1)",
    lineHighlight: "rgba(255, 255, 255, 0.04)",
    gutterBackground: "#16162a",
    gutterForeground: "#6b7280",
  },
  styles: [
    { tag: t.heading, color: "#22d3ee", fontWeight: "bold" },
    { tag: t.keyword, color: "#a78bfa" },
    { tag: t.comment, color: "#6b7280", fontStyle: "italic" },
    { tag: t.number, color: "#34d399" },
    { tag: t.meta, color: "#f59e0b" },
    { tag: t.propertyName, color: "#60a5fa" },
    { tag: t.escape, color: "#fb923c" },
    { tag: t.operator, color: "#94a3b8" },
  ],
});

/** Light theme variant for Sublarr's light mode. */
export const sublarrLightTheme = createTheme({
  theme: "light",
  settings: {
    background: "#f8fafc",
    foreground: "#1e293b",
    caret: "#0e7490",
    selection: "rgba(14, 116, 144, 0.2)",
    selectionMatch: "rgba(14, 116, 144, 0.1)",
    lineHighlight: "rgba(0, 0, 0, 0.03)",
    gutterBackground: "#f1f5f9",
    gutterForeground: "#94a3b8",
  },
  styles: [
    { tag: t.heading, color: "#0891b2", fontWeight: "bold" },
    { tag: t.keyword, color: "#7c3aed" },
    { tag: t.comment, color: "#9ca3af", fontStyle: "italic" },
    { tag: t.number, color: "#059669" },
    { tag: t.meta, color: "#d97706" },
    { tag: t.propertyName, color: "#2563eb" },
    { tag: t.escape, color: "#ea580c" },
    { tag: t.operator, color: "#64748b" },
  ],
});
