# -*- coding: utf-8 -*-
"""Audit Settings tsx files for potentially-untranslated hardcoded strings."""
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
SETTINGS_DIR = ROOT / "pages" / "Settings"
COMPONENTS_SETTINGS_DIR = ROOT / "components" / "settings"

files = [p for p in SETTINGS_DIR.rglob("*.tsx") if "__tests__" not in str(p)]
files += [p for p in COMPONENTS_SETTINGS_DIR.rglob("*.tsx") if "__tests__" not in str(p)]

JSX_TEXT = re.compile(r">\s*([A-Za-z][A-Za-z0-9 .'&/\-_+:!?,\u00c4-\u00fc]{1,80}?)\s*<")
ATTR_STR = re.compile(
    r'\b(title|placeholder|aria-label|label|alt)=["\']([^"\'{}\n]{2,80})["\']'
)
TOAST_CALL = re.compile(r'\btoast\(\s*["\']([^"\'{}\n]{3,80})["\']')
CONFIRM_CALL = re.compile(r'\bconfirm\(\s*["\']([^"\'{}\n]{3,100})["\']')

IGNORE_SKIP_IF_ATTR_CONTAINS = ["/", ".db", ":", "$", "{", "@", "http"]

hits: dict[str, list[tuple[int, str, str]]] = {}
for p in files:
    text = p.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.split("\n"), 1):
        s = line.lstrip()
        if s.startswith("//") or s.startswith("*"):
            continue
        for m in JSX_TEXT.finditer(line):
            txt = m.group(1).strip()
            if any(c in txt for c in "{}$"):
                continue
            if not re.search(r"[A-Za-z\u00c4-\u00fc]{3,}", txt):
                continue
            if re.match(r"^[A-Z][a-z]+$", txt):
                continue
            hits.setdefault(str(p), []).append((lineno, "TEXT", txt[:70]))
        for m in ATTR_STR.finditer(line):
            attr, val = m.group(1), m.group(2)
            if any(c in val for c in IGNORE_SKIP_IF_ATTR_CONTAINS):
                continue
            if not re.search(r"[A-Za-z\u00c4-\u00fc]{3,}", val):
                continue
            if val in ("button", "submit", "text", "password", "email", "checkbox"):
                continue
            hits.setdefault(str(p), []).append((lineno, f"ATTR[{attr}]", val[:70]))
        for m in TOAST_CALL.finditer(line):
            v = m.group(1)
            if re.search(r"[A-Za-z\u00c4-\u00fc]{3,}", v):
                hits.setdefault(str(p), []).append((lineno, "TOAST", v[:70]))
        for m in CONFIRM_CALL.finditer(line):
            v = m.group(1)
            if re.search(r"[A-Za-z\u00c4-\u00fc]{3,}", v):
                hits.setdefault(str(p), []).append((lineno, "CONFIRM", v[:70]))

total = 0
for path in sorted(hits):
    items = hits[path]
    rel = path.replace("\\", "/").split("/frontend/src/")[-1]
    print(f"\n[{rel}]  ({len(items)})")
    for ln, kind, hit in items[:25]:
        print(f"  L{ln:<4} {kind:<12} {hit}")
    if len(items) > 25:
        print(f"  ... +{len(items)-25} more")
    total += len(items)

print(f"\nGrand total suspect strings: {total}")
