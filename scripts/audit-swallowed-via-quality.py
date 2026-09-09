"""Find swallowed dialogue without needing the source subtitle.

The sibling-source audit (audit-swallowed-ass-lines.py) can only judge a
translation that has a source ASS lying next to it. Roughly half of the
German ASS files on a real install came from an embedded track instead, and
that source is inside the container file.

Those files carry a different reference: ``<output>.quality.json`` holds one
score per translated dialogue line. It is written AFTER the sanitizer ran, so

    scores in the sidecar  -  dialogue lines left in the file  =  lines lost

Two things this detector cannot see, stated so nobody mistakes a clean bill
for proof: a file whose sidecar predates the quality feature, and lost SIGN
lines (only translated dialogue is scored).

Calibrate before believing: ``--calibrate <listing>`` runs it against the
files the sibling audit already judged and reports where the two disagree.

Usage (inside the container):
    python3 audit-swallowed-via-quality.py /tmp/all-ass.txt [--calibrate]
"""

import json
import os
import re
import sys
from collections import defaultdict

MEDIA_ROOT = os.environ.get("AUDIT_MEDIA_ROOT", "/media")
SOURCE_LANGS = ("en", "eng", "ja", "jpn", "und", "es", "fr")
LANG_SUFFIX_RE = re.compile(r"\.([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)\.ass$")

def read_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="replace")


def dialog_styles(text):
    """Styles the translator itself treats as dialogue.

    Calibration 2026-09-09: a name-based guess ("Signs", "neo op enga top",
    …) flagged 116 files where the sibling audit found 13. On one of them the
    SOURCE already had zero Default lines and both files carried an identical
    4 201 events — the guess was wrong, not the file. So ask the classifier
    the translator actually used; it is importable here.
    """
    import pysubs2
    from ass_utils import classify_styles

    try:
        subs = pysubs2.SSAFile.from_string(text)
    except Exception:
        # A file pysubs2 will not parse cannot be judged here. Reported as
        # unjudged rather than silently counted as clean.
        return None
    dialog, _signs = classify_styles(subs)
    return set(dialog)


def dialogue_events_by_style(text, styles):
    n = 0
    for line in text.split("\n"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 4)
        if len(parts) >= 4 and parts[3].strip() in styles:
            n += 1
    return n


def scores_for(path):
    try:
        with open(path + ".quality.json", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return len(data) if isinstance(data, list) else None


def main():
    listing = sys.argv[1]
    calibrate = "--calibrate" in sys.argv

    by_base = defaultdict(dict)
    with open(listing, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            rel = line.strip().lstrip("./")
            if not rel:
                continue
            m = LANG_SUFFIX_RE.search(rel)
            if m:
                by_base[rel[: m.start()]][m.group(1).lower()] = os.path.join(MEDIA_ROOT, rel)

    german = {b: v for b, v in by_base.items() if "de" in v}
    with_source = {b for b, v in german.items() if any(s in v for s in SOURCE_LANGS)}

    selected = sorted(german) if calibrate else sorted(set(german) - with_source)
    scope = "files the sibling audit already judged" if calibrate else "files WITHOUT a sibling source"
    print(f"German ASS files: {len(german)}  ({len(with_source)} with a sibling source)")
    print(f"scope: {scope} -> {len(selected)}")
    print()

    no_sidecar = short = fine = unparseable = 0
    total_lost = 0
    findings = []

    for base in selected:
        path = german[base]["de"]
        n_scores = scores_for(path)
        if n_scores is None:
            no_sidecar += 1
            continue
        try:
            text = read_text(path)
        except OSError:
            no_sidecar += 1
            continue
        styles = dialog_styles(text)
        if styles is None:
            unparseable += 1
            continue
        n_lines = dialogue_events_by_style(text, styles)
        delta = n_scores - n_lines
        if delta > 0:
            short += 1
            total_lost += delta
            findings.append((delta, n_scores, n_lines, base))
        else:
            fine += 1

    print(f"no quality sidecar : {no_sidecar}")
    print(f"unparseable        : {unparseable}")
    print(f"consistent         : {fine}")
    print(f"short of dialogue  : {short}")
    print(f"dialogue lines lost: {total_lost}")
    print()
    for delta, n_scores, n_lines, base in sorted(findings, reverse=True)[:30]:
        print(f"  -{delta:5d}  ({n_scores} scored, {n_lines} left)  {base}")


if __name__ == "__main__":
    main()
