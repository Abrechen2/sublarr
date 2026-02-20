/**
 * SRT (SubRip) syntax highlighting tokenizer for CodeMirror 6.
 *
 * Classifies SRT format tokens:
 * - Cue numbers (digits only on a line) -> number
 * - Timestamps 00:00:00,000 -> number
 * - Arrow --> -> operator
 * - HTML-style tags <i>, </i>, <b>, <font...> -> meta
 */

import { StreamLanguage } from "@codemirror/language";

export const srtLanguage = StreamLanguage.define({
  token(stream) {
    // Skip leading whitespace
    if (stream.eatSpace()) return null;

    // Cue number: digits only on a line by itself
    if (stream.sol() && stream.match(/^\d+\s*$/)) return "number";

    // SRT timestamps: 00:00:00,000
    if (stream.match(/\d{2}:\d{2}:\d{2},\d{3}/)) return "number";

    // Arrow separator: -->
    if (stream.match(/-->/)) return "operator";

    // HTML-style formatting tags: <i>, </i>, <b>, </b>, <u>, </u>, <font...>
    if (stream.match(/<\/?[a-z][^>]*>/i)) return "meta";

    // Consume one character if nothing matched
    stream.next();
    return null;
  },
});
