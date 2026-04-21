# -*- coding: utf-8 -*-
"""Remove duplicate useTranslation declarations in the same function scope."""
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path("frontend/src")
files = [
    p
    for p in ROOT.rglob("*.tsx")
    if "__tests__" not in str(p) and ".test." not in str(p)
]

FUNC_DECL_RE = re.compile(r"^(?:export\s+)?function\s+[A-Z]\w*\s*\(")
ARROW_FUNC_DECL_RE = re.compile(r"^(?:export\s+)?const\s+[A-Z]\w*\s*[:=]")
DECL_LINE_RE = re.compile(
    r"const\s*\{\s*([^}]+?)\s*\}\s*=\s*useTranslation\s*\(\s*['\"]([^'\"]+)['\"]"
)

total_removed = 0
for p in files:
    raw = p.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw[:200] else b"\n"
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")
    functions = []
    for i, line in enumerate(lines):
        if FUNC_DECL_RE.match(line) or ARROW_FUNC_DECL_RE.match(line):
            body_open = None
            for k in range(i, min(i + 60, len(lines))):
                s = lines[k].rstrip()
                if re.search(r"\)\s*\{$", s) or re.search(r"=>\s*\{$", s):
                    body_open = k
                    break
            if body_open is None:
                continue
            depth = 0
            end_idx = None
            for k in range(body_open, len(lines)):
                for ch in lines[k]:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end_idx = k
                            break
                if end_idx is not None:
                    break
            if end_idx is not None:
                functions.append((body_open, end_idx))
    to_remove = set()
    for body_open, body_close in functions:
        seen = {}
        for k in range(body_open + 1, body_close):
            m = DECL_LINE_RE.search(lines[k])
            if m:
                aliases = m.group(1).replace(" ", "")
                ns = m.group(2)
                key = (aliases, ns)
                if key in seen:
                    to_remove.add(k)
                else:
                    seen[key] = k
    if to_remove:
        for k in sorted(to_remove, reverse=True):
            del lines[k]
        new_text = "\n".join(lines)
        if eol == b"\r\n":
            new_text = new_text.replace("\n", "\r\n")
        p.write_bytes(new_text.encode("utf-8"))
        rel = str(p).replace("\\", "/").split("/frontend/src/")[-1]
        print(f"{rel}: removed {len(to_remove)} duplicate decl(s)")
        total_removed += len(to_remove)

print(f"\nTotal duplicates removed: {total_removed}")
