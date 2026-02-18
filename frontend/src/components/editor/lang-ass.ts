/**
 * ASS (Advanced SubStation Alpha) syntax highlighting tokenizer for CodeMirror 6.
 *
 * Classifies ASS format tokens:
 * - Section headers [Script Info], [V4+ Styles], [Events] -> heading
 * - Semicolon comment lines -> comment
 * - Event keywords (Dialogue:, Comment:, Format:, Style:) -> keyword
 * - Metadata Key: lines -> propertyName
 * - Override tags {...} -> meta
 * - Timestamps H:MM:SS.CC -> number
 * - Line break markers \N, \n -> escape
 */

import { StreamLanguage } from "@codemirror/language";

export const assLanguage = StreamLanguage.define({
  token(stream) {
    // Skip leading whitespace
    if (stream.eatSpace()) return null;

    // Section headers: [Script Info], [V4+ Styles], [Events], [Fonts], [Graphics]
    if (stream.sol() && stream.match(/^\[.*\]\s*$/)) return "heading";

    // Comment lines (semicolons at start of line in Script Info section)
    if (stream.sol() && stream.peek() === ";") {
      stream.skipToEnd();
      return "comment";
    }

    // Event type keywords at start of line
    if (stream.sol() && stream.match(/^(Dialogue|Comment|Format|Style):\s*/)) {
      return "keyword";
    }

    // Metadata key: value lines at start of line (Script Info section)
    if (stream.sol() && stream.match(/^[A-Za-z][A-Za-z0-9 ]*:/)) {
      return "propertyName";
    }

    // Override tags: {...}
    if (stream.match(/\{[^}]*\}/)) return "meta";

    // ASS timestamps: H:MM:SS.CC
    if (stream.match(/\d:\d{2}:\d{2}\.\d{2}/)) return "number";

    // ASS line break markers: \N (hard) and \n (soft)
    if (stream.match(/\\[Nn]/)) return "escape";

    // Consume one character if nothing matched
    stream.next();
    return null;
  },
  languageData: {
    commentTokens: { line: ";" },
  },
});
