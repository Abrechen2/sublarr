# -*- coding: utf-8 -*-
"""For each React function component, ensure it declares the hooks it uses."""
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
files = [
    p
    for p in ROOT.rglob("*.tsx")
    if "__tests__" not in str(p) and ".test." not in str(p)
]

FUNC_DECL_RE = re.compile(
    r"^(?:export\s+)?function\s+(?P<name>[A-Z]\w*)\s*\("
)

USAGE_RE = re.compile(r"\b(?P<alias>t|tc|tCommon|tHelp|tUI|tn)\s*\(\s*['\"](?P<key>[^'\"]+)['\"]")

NS_MAP = {
    "ui.": "common",
    "actions.": "common",
    "common.": "common",
    "library.": "library",
    "settings.": "settings",
    "activity.": "activity",
    "editor.": "editor",
    "wanted.": "activity",
    "wanted_row.": "activity",
    "wanted_filters.": "activity",
}


def infer_ns(key: str) -> str:
    for prefix, ns in NS_MAP.items():
        if key.startswith(prefix):
            return ns
    return "common"


def find_function_body(lines: list[str], decl_line_idx: int) -> tuple[int, int] | None:
    """Return (body_open_idx, body_close_idx). body_open is line with `) {` ending the sig."""
    body_open = None
    for k in range(decl_line_idx, min(decl_line_idx + 60, len(lines))):
        stripped = lines[k].rstrip()
        if re.search(r"\)\s*\{$", stripped) or re.search(r"\):\s*[^{]*\s*\{$", stripped):
            body_open = k
            break
    if body_open is None:
        return None
    # Find matching close by counting braces starting at body_open
    depth = 0
    for k in range(body_open, len(lines)):
        for ch in lines[k]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return (body_open, k)
    return None


total_fixes = 0
for p in files:
    raw = p.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw[:200] else b"\n"
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")
    # Find all PascalCase function declarations
    functions = []  # (name, decl_line_idx, body_open, body_close)
    for i, line in enumerate(lines):
        m = FUNC_DECL_RE.match(line)
        if m:
            name = m.group("name")
            body = find_function_body(lines, i)
            if body:
                functions.append((name, i, body[0], body[1]))
    if not functions:
        continue
    # For each function, check usages within its body and declarations
    any_change = False
    # Process in reverse line order so insertions don't shift later positions
    for name, decl_idx, body_open, body_close in reversed(functions):
        body_text = "\n".join(lines[body_open + 1 : body_close])
        # Usages in body
        aliases_used: dict[str, str] = {}  # alias -> ns
        for m in USAGE_RE.finditer(body_text):
            alias = m.group("alias")
            key = m.group("key")
            if alias not in aliases_used:
                aliases_used[alias] = infer_ns(key)
        if not aliases_used:
            continue
        # Check: is alias already declared within body? Or received as prop?
        # Props: check the function signature lines
        sig_text = "\n".join(lines[decl_idx : body_open + 1])
        to_add = {}
        for alias, ns in aliases_used.items():
            decl_re1 = rf"const\s*\{{\s*[^}}]*\bt\s*:\s*{re.escape(alias)}\s*[,}}]"
            decl_re2 = (
                rf"const\s*\{{\s*[^}}]*\b{re.escape(alias)}\s*[,}}]\s*\}}\s*=\s*useTranslation"
                if alias == "t"
                else None
            )
            declared_in_body = bool(re.search(decl_re1, body_text)) or (
                decl_re2 and bool(re.search(decl_re2, body_text))
            )
            # Prop destructure: { ..., t, ... } or { ..., t: alias, ... } in signature
            prop_re = rf"\{{[^}}]*\b{re.escape(alias)}\s*[,}}]"
            prop_re_alias = (
                rf"\{{[^}}]*\bt\s*:\s*{re.escape(alias)}\s*[,}}]" if alias != "t" else None
            )
            from_prop = bool(re.search(prop_re, sig_text)) or (
                prop_re_alias and bool(re.search(prop_re_alias, sig_text))
            )
            if not declared_in_body and not from_prop:
                to_add[alias] = ns
        if not to_add:
            continue
        # Determine indent from body
        indent = "  "
        for k in range(body_open + 1, min(body_open + 6, body_close)):
            mm = re.match(r"^(\s+)\S", lines[k])
            if mm:
                indent = mm.group(1)
                break
        # Build decl lines
        decls = []
        for alias, ns in to_add.items():
            if alias == "t":
                decls.append(f"{indent}const {{ t }} = useTranslation('{ns}')")
            else:
                decls.append(f"{indent}const {{ t: {alias} }} = useTranslation('{ns}')")
        # Insert after body_open
        insert_pos = body_open + 1
        for d in reversed(decls):
            lines.insert(insert_pos, d)
        any_change = True
        total_fixes += len(decls)
        print(f"  +{len(decls)} in {p.name}::{name} — {list(to_add.items())}")
    if any_change:
        # Ensure import
        has_import = any("useTranslation" in l and "react-i18next" in l for l in lines[:60])
        if not has_import:
            last_import = 0
            for k, line in enumerate(lines[:80]):
                if re.match(r"^\s*import\s+", line):
                    last_import = k
            lines.insert(last_import + 1, "import { useTranslation } from 'react-i18next'")
        new_text = "\n".join(lines)
        if eol == b"\r\n":
            new_text = new_text.replace("\n", "\r\n")
        p.write_bytes(new_text.encode("utf-8"))

print(f"\nTotal hook declarations added: {total_fixes}")
