#!/usr/bin/env python3
"""One-off remediation: restore SRT/VTT timecode arrows corrupted to '--&gt;'.

Pre-existing sanitizer bug (#44, 0.15.2-beta) HTML-escaped the '>' in the
'-->' timecode separator on every downloaded SRT, producing '--&gt;' and
breaking the cue. The bug is fixed forward in subtitle_sanitizer.py; this
script repairs files already on disk.

Surgical + safe: only un-escapes '--&gt;' when flanked by two timestamps
(timecode lines never carry user text), mirroring the forward fix. Cue-text
entity escaping is intentionally left untouched. Idempotent — a second run
finds nothing to do. Each modified file is backed up to '<path>.timecodebak'
(skipped if that backup already exists).

Usage:
    python3 remediate_srt_timecode.py <list-file>            # dry-run (default)
    python3 remediate_srt_timecode.py <list-file> --apply    # write changes

<list-file>: newline-separated absolute paths to candidate .srt/.vtt files.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

_TS = r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}"
_ARROW_RE = re.compile(rf"({_TS}[ \t]*)--&gt;([ \t]*{_TS})".encode())


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    null_delim = "-0" in sys.argv
    if not args:
        print(__doc__)
        return 2
    list_file = args[0]

    with open(list_file, "rb") as fh:
        blob = fh.read()
    # -0: NUL-delimited input (robust against newlines embedded in filenames).
    parts = blob.split(b"\x00") if null_delim else blob.splitlines()
    paths = [p.strip(b"\r\n") if not null_delim else p for p in parts if p.strip()]

    changed = skipped_clean = errors = backed_up = 0
    samples: list[str] = []

    for raw in paths:
        path = raw.decode("utf-8", "surrogateescape")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            print(f"ERR  read {path}: {e}")
            errors += 1
            continue

        fixed, n = _ARROW_RE.subn(rb"\1-->\2", data)
        if n == 0:
            skipped_clean += 1
            continue

        changed += 1
        if len(samples) < 5:
            samples.append(f"  {path}  ({n} arrow(s))")

        if apply:
            bak = path + ".timecodebak"
            try:
                if not os.path.exists(bak):
                    shutil.copy2(path, bak)
                    backed_up += 1
                tmp = path + ".tmp-remediate"
                with open(tmp, "wb") as fh:
                    fh.write(fixed)
                os.replace(tmp, path)
            except OSError as e:
                print(f"ERR  write {path}: {e}")
                errors += 1

    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"\n=== {mode} ===")
    print(f"candidates : {len(paths)}")
    print(f"to fix     : {changed}")
    print(f"already ok : {skipped_clean}")
    print(f"errors     : {errors}")
    if apply:
        print(f"backed up  : {backed_up} (<path>.timecodebak)")
    if samples:
        print("samples:")
        print("\n".join(samples))
    if not apply and changed:
        print("\nRe-run with --apply to write changes.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
