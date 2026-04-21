# -*- coding: utf-8 -*-
"""Find components that use t()/tc()/tCommon()/tHelp() without declaring them."""
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
files = [p for p in ROOT.rglob("*.tsx") if "__tests__" not in str(p) and ".test." not in str(p)]
files += [p for p in ROOT.rglob("*.ts") if "__tests__" not in str(p) and ".test." not in str(p) and ".d.ts" not in str(p)]

# Aliases we might encounter
aliases = ["t", "tc", "tCommon", "tHelp", "tUI", "tn", "tUi"]

for p in files:
    text = p.read_text(encoding="utf-8", errors="replace")
    for alias in aliases:
        # Find usages of alias(...)
        usage_re = re.compile(rf"\b{re.escape(alias)}\s*\(")
        if not usage_re.search(text):
            continue
        # Check if it is declared somewhere: either
        #   const { <alias> } = useTranslation(...)
        #   const { t: <alias> } = useTranslation(...)
        #   ({ ..., <alias>, ... }) => ...   (as destructured prop)
        #   function Foo({ ..., <alias>, ... }: ...) { ... }
        decl_patterns = [
            rf"const\s*\{{[^}}]*\b{re.escape(alias)}\b[^}}]*\}}\s*=\s*useTranslation",
            rf"const\s*\{{\s*t\s*:\s*{re.escape(alias)}\s*\}}\s*=\s*useTranslation",
            rf"\{{[^}}]*\b{re.escape(alias)}\b[^}}]*\}}\s*(?::[^)]*)?\)",  # destructure in param
            rf"\bfunction\s+\w+\([^)]*\b{re.escape(alias)}\b",  # func args (unnamed destructure)
        ]
        declared = any(re.search(p, text) for p in decl_patterns)
        # Also check for simple prop name without {}, e.g. "(t) =>" or "(t, ...)"
        if not declared and alias in ("t",):
            if re.search(r"\(\s*t\s*[,)]", text) or re.search(r"\bt\b\s*:\s*[A-Z]", text):
                declared = True
        if not declared:
            # Likely undeclared — report
            # Count usages and find first usage line
            for lineno, line in enumerate(text.split("\n"), 1):
                if usage_re.search(line):
                    rel = str(p).replace("\\", "/").split("/frontend/src/")[-1]
                    print(f"{rel}:{lineno}  uses {alias}(...)  → no declaration found")
                    break
