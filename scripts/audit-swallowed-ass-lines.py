"""Measure the dialogue the old sanitizer swallowed between two drawing tags.

Until 1.14.0 the ASS sanitizer stripped drawing blocks with one pattern that
was allowed to span the whole file:

    \\{[^}]*\\\\p[1-9][^}]*\\}.*?\\{[^}]*\\\\p0[^}]*\\}      (re.DOTALL)

When the opener sat on one Dialogue line and the next closer on another, every
line in between was deleted along with the block. This script finds the files
that lost lines that way and says how many.

It does NOT run the old pattern — that is the quadratic scan the fix removed.
It walks the tags once, in the order the old engine would have consumed them,
which yields the same spans in linear time.

The reference for "how many lines should be here" is the source subtitle next
to it: translation replaces the text of an event, never the number of events,
so a translated ASS with fewer Dialogue lines than its source lost them.

Usage (inside the container, where /media is mounted):
    python3 audit-swallowed-ass-lines.py /tmp/all-ass.txt [--limit N]

Reads paths relative to the media root, one per line.
"""

import os
import re
import sys
from collections import defaultdict

TAG_RE = re.compile(r"\{[^}]*\}")
DRAW_ON_RE = re.compile(r"\\p[1-9]", re.IGNORECASE)
DRAW_OFF_RE = re.compile(r"\\p0", re.IGNORECASE)

MEDIA_ROOT = os.environ.get("AUDIT_MEDIA_ROOT", "/media")
# Languages that can act as the source of a German translation.
SOURCE_LANGS = ("en", "eng", "ja", "jpn", "und", "es", "fr")
LANG_SUFFIX_RE = re.compile(r"\.([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)\.ass$")


def read_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="replace")


def swallowed_newlines(text):
    """Lines the old spanning pattern would have deleted between events.

    Mirrors the old engine: consume tags in order; an opener starts a block,
    the next closer ends it, and everything in between goes. Only newlines
    inside a span count — a block opened and closed on one line took no
    dialogue with it, which was the intended behaviour.
    """
    lost = 0
    spans = 0
    start = None
    for tag in TAG_RE.finditer(text):
        body = tag.group()
        if start is None:
            if DRAW_ON_RE.search(body):
                start = tag.start()
        elif DRAW_OFF_RE.search(body):
            inner = text.count("\n", start, tag.end())
            if inner:
                lost += inner
                spans += 1
            start = None
    return lost, spans


def dialogue_lines(text):
    return text.count("\nDialogue:") + (1 if text.startswith("Dialogue:") else 0)


# A style carrying spoken lines rather than typesetting. Loss here is a viewer
# losing subtitles; loss in a Signs/karaoke style is lost decoration.
DIALOG_STYLE_RE = re.compile(r"^(default|main|dialog|dialogue|alt|top|italic)\b", re.IGNORECASE)


def dialog_style_lines(text):
    """Count Dialogue events whose style looks like spoken dialogue."""
    n = 0
    for line in text.split("\n"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 4)
        if len(parts) < 4:
            continue
        style = parts[3].strip()
        if DIALOG_STYLE_RE.match(style) or DIALOG_STYLE_RE.match(style.replace("Default - ", "")):
            n += 1
    return n


def main():
    listing = sys.argv[1]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    by_base = defaultdict(dict)
    with open(listing, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            rel = line.strip().lstrip("./")
            if not rel:
                continue
            m = LANG_SUFFIX_RE.search(rel)
            if not m:
                continue
            by_base[rel[: m.start()]][m.group(1).lower()] = os.path.join(MEDIA_ROOT, rel)

    pairs = [(b, v) for b, v in by_base.items() if "de" in v and any(s in v for s in SOURCE_LANGS)]
    pairs.sort()
    if limit:
        pairs = pairs[:limit]

    print(f"bases with a German ASS and a source ASS: {len(pairs)}")
    print(f"(of {len(by_base)} bases carrying any ASS at all)")
    print()

    checked = damaged = unreadable = spoken_damaged = 0
    total_lost = total_spoken_lost = 0
    findings = []

    for base, langs in pairs:
        src_lang = next(s for s in SOURCE_LANGS if s in langs)
        try:
            de_text = read_text(langs["de"])
            src_text = read_text(langs[src_lang])
        except OSError:
            unreadable += 1
            continue

        checked += 1
        expected_lost, spans = swallowed_newlines(src_text)
        if not expected_lost:
            continue

        de_n = dialogue_lines(de_text)
        src_n = dialogue_lines(src_text)
        delta = src_n - de_n
        if delta > 0:
            spoken_lost = dialog_style_lines(src_text) - dialog_style_lines(de_text)
            damaged += 1
            total_lost += delta
            total_spoken_lost += spoken_lost
            if spoken_lost > 0:
                spoken_damaged += 1
            findings.append((delta, spoken_lost, expected_lost, spans, src_lang, base))

    print(f"checked                    : {checked}")
    print(f"unreadable                 : {unreadable}")
    print(f"files missing events       : {damaged}")
    print(f"events lost (all styles)   : {total_lost}")
    print(f"files missing SPOKEN lines : {spoken_damaged}")
    print(f"spoken lines lost          : {total_spoken_lost}")
    print()
    print("worst offenders (spoken loss is what a viewer actually misses):")
    for delta, spoken, expected, spans, src_lang, base in sorted(findings, reverse=True)[:15]:
        print(
            f"  -{delta:6d} events, {spoken:5d} of them spoken "
            f"(pattern predicts {expected} over {spans} span(s), src={src_lang})"
        )
        print(f"          {base}")
    if any(f[1] > 0 for f in findings):
        print()
        print("files that lost SPOKEN lines:")
        for delta, spoken, _expected, _spans, src_lang, base in sorted(findings, reverse=True):
            if spoken > 0:
                print(f"  -{spoken:5d} spoken (of {delta} events, src={src_lang})  {base}")


if __name__ == "__main__":
    main()
