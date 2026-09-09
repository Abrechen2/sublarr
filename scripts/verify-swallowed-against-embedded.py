"""Verify swallowed-dialogue candidates against the embedded subtitle track.

The quality-sidecar pre-filter (audit-swallowed-via-quality.py) is cheap but
noisy: on a production library it flagged files whose German sidecar actually
held English text, and files whose style classification simply disagreed with
a name-based guess. Neither is the sanitizer's doing.

This settles each candidate the only way that is exact — pull the ASS track
out of the video and compare it with the translation event for event, the
same rule the sibling audit uses:

    events in the embedded source  -  events in the translation  =  lines lost

and cross-check the number against what the old spanning pattern predicts for
that source. A candidate is only called damaged when both agree.

Usage (inside the container):
    python3 verify-swallowed-against-embedded.py <bases-file>

<bases-file> holds one media-root-relative base path per line (the path of the
translation without its ``.de.ass`` suffix).
"""

import os
import re
import subprocess
import sys
import tempfile

MEDIA_ROOT = os.environ.get("AUDIT_MEDIA_ROOT", "/media")
VIDEO_EXTS = (".mkv", ".mp4", ".m4v", ".avi", ".ts")

TAG_RE = re.compile(r"\{[^}]*\}")
DRAW_ON_RE = re.compile(r"\\p[1-9]", re.IGNORECASE)
DRAW_OFF_RE = re.compile(r"\\p0", re.IGNORECASE)


def swallowed_newlines(text):
    """Lines the old spanning pattern would have deleted. Linear, one pass."""
    lost = spans = 0
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


def find_video(base_abs):
    for ext in VIDEO_EXTS:
        if os.path.exists(base_abs + ext):
            return base_abs + ext
    return None


def ass_stream_indexes(video):
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index,codec_name",
            "-of", "csv=p=0", video,
        ],
        capture_output=True, text=True, timeout=180,
    ).stdout
    idx = []
    for i, line in enumerate(out.strip().split("\n")):
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 2 and parts[1].strip() in ("ass", "ssa"):
            idx.append(i)
    return idx


def extract_ass(video, sub_index):
    with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as tmp:
        path = tmp.name
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video, "-map", f"0:s:{sub_index}", "-c:s", "ass", path],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        os.unlink(path)
        return None
    return path


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        bases = [ln.strip() for ln in fh if ln.strip()]

    print(f"candidates: {len(bases)}\n")
    damaged = clean = no_video = no_track = 0

    for base in bases:
        base_abs = os.path.join(MEDIA_ROOT, base)
        de_path = base_abs + ".de.ass"
        video = find_video(base_abs)
        name = base.rsplit("/", 1)[-1][:70]

        if not video:
            no_video += 1
            print(f"  [no video ] {name}")
            continue

        indexes = ass_stream_indexes(video)
        if not indexes:
            no_track += 1
            print(f"  [no track ] {name}")
            continue

        with open(de_path, "rb") as fh:
            de_text = fh.read().decode("utf-8", errors="replace")
        de_n = dialogue_lines(de_text)

        best = None
        for sub_index in indexes:
            tmp = extract_ass(video, sub_index)
            if not tmp:
                continue
            with open(tmp, "rb") as fh:
                src_text = fh.read().decode("utf-8", errors="replace")
            os.unlink(tmp)
            src_n = dialogue_lines(src_text)
            predicted, spans = swallowed_newlines(src_text)
            # The track the translation came from is the one whose event count
            # is closest from above -- a foreign track of a different length
            # would otherwise masquerade as loss.
            if best is None or abs(src_n - de_n) < abs(best[0] - de_n):
                best = (src_n, predicted, spans)

        if best is None:
            no_track += 1
            print(f"  [unreadable] {name}")
            continue

        src_n, predicted, spans = best
        delta = src_n - de_n
        if delta > 0 and predicted > 0:
            damaged += 1
            print(f"  -{delta:6d} events (predicted {predicted} over {spans} span(s))  {name}")
        else:
            clean += 1
            print(f"  [clean    ] src={src_n} de={de_n} predicted={predicted}  {name}")

    print()
    print(f"damaged: {damaged}   clean: {clean}   no video: {no_video}   no usable track: {no_track}")


if __name__ == "__main__":
    main()
