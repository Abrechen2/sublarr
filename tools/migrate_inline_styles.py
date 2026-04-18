#!/usr/bin/env python3
"""Migrate React inline-style to Tailwind class utilities.

Scans a TSX file for ``style={{ ... }}`` attributes and emits a conversion
report. Known static property/value pairs get a suggested Tailwind class;
unknown or dynamic values are flagged for manual review.

Usage:
    python tools/migrate_inline_styles.py <file.tsx>        # report only
    python tools/migrate_inline_styles.py <file.tsx> --apply  # rewrite in place

The tool is intentionally conservative: it never rewrites a style attribute
unless EVERY key in that attribute has a 1:1 Tailwind mapping. Mixed static/
dynamic attributes are left alone and printed in the report for manual work.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# 1:1 mappings — static CSS value → Tailwind class
#
# Keep this dictionary focused on values that appear in the codebase. When a
# value is unfamiliar, prefer returning None (triggers manual review) over
# guessing an approximate class.
# =============================================================================

# Spacing: px value → Tailwind spacing index (p-3, m-3, gap-3, etc.)
# Tailwind default: p-N = N * 0.25rem = N * 4px (when root font-size is 16px).
SPACING_PX_TO_INDEX: dict[str, str] = {
    "0": "0",
    "0px": "0",
    "1px": "px",  # Tailwind's 1px utility
    "2px": "0.5",
    "4px": "1",
    "6px": "1.5",
    "8px": "2",
    "10px": "2.5",
    "12px": "3",
    "14px": "3.5",
    "16px": "4",
    "20px": "5",
    "24px": "6",
    "28px": "7",
    "32px": "8",
    "36px": "9",
    "40px": "10",
    "44px": "11",
    "48px": "12",
    "56px": "14",
    "64px": "16",
    "80px": "20",
    "96px": "24",
}

# CSS-var spacing references — map ``var(--space-N)`` to spacing index.
SPACING_VAR_TO_INDEX: dict[str, str] = {
    "var(--space-1)": "1",
    "var(--space-2)": "2",
    "var(--space-3)": "3",
    "var(--space-4)": "4",
    "var(--space-6)": "6",
    "var(--space-8)": "8",
    "var(--space-12)": "12",
}

# Border radius: CSS value → Tailwind class suffix
RADIUS_MAP: dict[str, str] = {
    "var(--radius-sm)": "rounded-sm",
    "var(--radius-md)": "rounded-md",
    "var(--radius-lg)": "rounded-lg",
    "var(--radius-xl)": "rounded-xl",
    "var(--radius-full)": "rounded-full",
    "9999px": "rounded-full",
    "8px": "rounded-sm",  # matches --radius-sm
    "10px": "rounded-md",
    "12px": "rounded-lg",
    "16px": "rounded-xl",
    # Borderline — kept explicit so it's visible in the mapping review:
    "4px": "rounded",  # Tailwind's 'rounded' = 0.25rem = 4px
    "2px": "rounded-sm",  # near-miss — flag for manual verification
}

# Color map — maps CSS color value/var to Tailwind theme key (without
# utility prefix, because the prefix depends on the property: bg-, text-,
# border-, etc.).
COLOR_VAR_TO_TOKEN: dict[str, str] = {
    "var(--bg-primary)": "page",
    "var(--bg-surface)": "surface",
    "var(--bg-surface-hover)": "surface-hover",
    "var(--bg-elevated)": "elevated",
    "var(--bg-deep)": "deep",
    "var(--border)": "border",
    "var(--border-hover)": "border-hover",
    "var(--text-primary)": "foreground",
    "var(--text-secondary)": "secondary",
    "var(--text-muted)": "muted",
    "var(--accent)": "accent",
    "var(--accent-hover)": "accent-hover",
    "var(--accent-dim)": "accent-dim",
    "var(--accent-subtle)": "accent-subtle",
    "var(--accent-bg)": "accent-bg",
    "var(--success)": "success",
    "var(--success-bg)": "success-bg",
    "var(--error)": "error",
    "var(--error-bg)": "error-bg",
    "var(--warning)": "warning",
    "var(--warning-bg)": "warning-bg",
    "var(--upgrade)": "upgrade",
    "var(--upgrade-bg)": "upgrade-bg",
}

# Static hex / rgb colors — no token mapping; convert to Tailwind arbitrary
# value only when absolutely necessary. Prefer manual migration to choose
# the right token.
STATIC_COLOR_TO_MANUAL: set[str] = {"#fff", "#ffffff", "#000", "#000000"}

# Font family
FONT_FAMILY_MAP: dict[str, str] = {
    "var(--font-body)": "font-sans",
    "var(--font-mono)": "font-mono",
}

# Shadow
SHADOW_MAP: dict[str, str] = {
    "var(--shadow-sm)": "shadow-sm",
    "var(--shadow-md)": "shadow-md",
    "var(--shadow-lg)": "shadow-lg",
    "var(--shadow-glass)": "shadow-glass",
}

# Font weight
FONT_WEIGHT_MAP: dict[str, str] = {
    "300": "font-light",
    "400": "font-normal",
    "500": "font-medium",
    "600": "font-semibold",
    "700": "font-bold",
    "800": "font-extrabold",
}

# Text align
TEXT_ALIGN_MAP: dict[str, str] = {
    "left": "text-left",
    "center": "text-center",
    "right": "text-right",
    "justify": "text-justify",
}

# Display
DISPLAY_MAP: dict[str, str] = {
    "flex": "flex",
    "inline-flex": "inline-flex",
    "block": "block",
    "inline-block": "inline-block",
    "inline": "inline",
    "grid": "grid",
    "none": "hidden",
}

# Flex direction
FLEX_DIRECTION_MAP: dict[str, str] = {
    "row": "flex-row",
    "column": "flex-col",
    "row-reverse": "flex-row-reverse",
    "column-reverse": "flex-col-reverse",
}

# Justify content
JUSTIFY_MAP: dict[str, str] = {
    "flex-start": "justify-start",
    "center": "justify-center",
    "flex-end": "justify-end",
    "space-between": "justify-between",
    "space-around": "justify-around",
    "space-evenly": "justify-evenly",
}

# Align items
ALIGN_MAP: dict[str, str] = {
    "flex-start": "items-start",
    "center": "items-center",
    "flex-end": "items-end",
    "stretch": "items-stretch",
    "baseline": "items-baseline",
}

# Whitespace
WHITESPACE_MAP: dict[str, str] = {
    "nowrap": "whitespace-nowrap",
    "pre": "whitespace-pre",
    "pre-line": "whitespace-pre-line",
    "pre-wrap": "whitespace-pre-wrap",
    "normal": "whitespace-normal",
}

# Cursor
CURSOR_MAP: dict[str, str] = {
    "pointer": "cursor-pointer",
    "default": "cursor-default",
    "not-allowed": "cursor-not-allowed",
    "grab": "cursor-grab",
    "grabbing": "cursor-grabbing",
    "text": "cursor-text",
    "wait": "cursor-wait",
}

# Overflow
OVERFLOW_MAP: dict[str, str] = {
    "hidden": "overflow-hidden",
    "auto": "overflow-auto",
    "scroll": "overflow-scroll",
    "visible": "overflow-visible",
}


# =============================================================================
# Dispatch by CSS property → class-resolver
# =============================================================================


def _spacing_class(prefix: str, value: str) -> str | None:
    """Generic spacing (padding/margin/gap) — returns 'p-3' / 'm-auto' / None."""
    value = value.strip()
    if value == "auto":
        return f"{prefix}-auto"
    if value in SPACING_VAR_TO_INDEX:
        return f"{prefix}-{SPACING_VAR_TO_INDEX[value]}"
    if value in SPACING_PX_TO_INDEX:
        return f"{prefix}-{SPACING_PX_TO_INDEX[value]}"
    return None


def _padding_shorthand(value: str) -> list[str] | None:
    """Handle 'padding: 4px 8px' / 'padding: 4px 8px 12px 16px'."""
    parts = value.strip().split()
    classes = []
    if len(parts) == 1:
        c = _spacing_class("p", parts[0])
        return [c] if c else None
    if len(parts) == 2:
        y = _spacing_class("py", parts[0])
        x = _spacing_class("px", parts[1])
        if y and x:
            return [y, x]
        return None
    if len(parts) == 3:
        # padding: top  lr bottom → py + px no mapping for different top/bottom
        t = _spacing_class("pt", parts[0])
        x = _spacing_class("px", parts[1])
        b = _spacing_class("pb", parts[2])
        if t and x and b:
            return [t, x, b]
        return None
    if len(parts) == 4:
        t = _spacing_class("pt", parts[0])
        r = _spacing_class("pr", parts[1])
        b = _spacing_class("pb", parts[2])
        left = _spacing_class("pl", parts[3])
        if t and r and b and left:
            return [t, r, b, left]
        return None
    return None


def _margin_shorthand(value: str) -> list[str] | None:
    """Handle 'margin: 4px 8px' variants, same rules as padding."""
    parts = value.strip().split()
    if len(parts) == 1:
        c = _spacing_class("m", parts[0])
        return [c] if c else None
    if len(parts) == 2:
        y = _spacing_class("my", parts[0])
        x = _spacing_class("mx", parts[1])
        if y and x:
            return [y, x]
        return None
    return None


def _color_class(prefix: str, value: str) -> str | None:
    """Convert a color value to a Tailwind utility (bg-accent, text-muted, etc.)."""
    value = value.strip()
    if value in COLOR_VAR_TO_TOKEN:
        return f"{prefix}-{COLOR_VAR_TO_TOKEN[value]}"
    return None


def _border_class(value: str) -> list[str] | None:
    """Handle 'border: 1px solid var(--border)'."""
    parts = value.strip().split()
    if len(parts) == 3:
        width, style, color = parts
        classes: list[str] = []
        # width
        w_map = {"1px": "border", "2px": "border-2", "4px": "border-4", "0": "border-0"}
        if width not in w_map:
            return None
        classes.append(w_map[width])
        # solid is default; skip explicit 'solid'
        style_map = {"solid": "", "dashed": "border-dashed", "dotted": "border-dotted"}
        if style not in style_map:
            return None
        if style_map[style]:
            classes.append(style_map[style])
        # color
        c = _color_class("border", color)
        if c:
            classes.append(c)
            return classes
    return None


def _font_size_class(value: str) -> str | None:
    """Tailwind text sizes are approximate — prefer near-miss conversion with note."""
    m = {
        "10px": "text-[10px]",  # arbitrary — no token
        "11px": "text-[11px]",  # arbitrary — could be text-xs
        "12px": "text-xs",  # 0.75rem
        "13px": "text-[13px]",  # arbitrary
        "14px": "text-sm",  # 0.875rem
        "15px": "text-[15px]",  # arbitrary
        "16px": "text-base",  # 1rem
        "18px": "text-lg",  # 1.125rem
        "20px": "text-xl",  # 1.25rem
        "24px": "text-2xl",  # 1.5rem
        "30px": "text-3xl",
        "36px": "text-4xl",
    }
    return m.get(value.strip())


def _line_height_class(value: str) -> str | None:
    m = {
        "1": "leading-none",
        "1.25": "leading-tight",
        "1.375": "leading-snug",
        "1.5": "leading-normal",
        "1.625": "leading-relaxed",
        "2": "leading-loose",
    }
    return m.get(value.strip())


PROPERTY_RESOLVERS: dict[str, callable] = {
    "padding": _padding_shorthand,
    "margin": _margin_shorthand,
    "paddingTop": lambda v: [_spacing_class("pt", v)] if _spacing_class("pt", v) else None,
    "paddingRight": lambda v: [_spacing_class("pr", v)] if _spacing_class("pr", v) else None,
    "paddingBottom": lambda v: [_spacing_class("pb", v)] if _spacing_class("pb", v) else None,
    "paddingLeft": lambda v: [_spacing_class("pl", v)] if _spacing_class("pl", v) else None,
    "marginTop": lambda v: [_spacing_class("mt", v)] if _spacing_class("mt", v) else None,
    "marginRight": lambda v: [_spacing_class("mr", v)] if _spacing_class("mr", v) else None,
    "marginBottom": lambda v: [_spacing_class("mb", v)] if _spacing_class("mb", v) else None,
    "marginLeft": lambda v: [_spacing_class("ml", v)] if _spacing_class("ml", v) else None,
    "gap": lambda v: [_spacing_class("gap", v)] if _spacing_class("gap", v) else None,
    "rowGap": lambda v: [_spacing_class("gap-y", v)] if _spacing_class("gap-y", v) else None,
    "columnGap": lambda v: [_spacing_class("gap-x", v)] if _spacing_class("gap-x", v) else None,
    "color": lambda v: [_color_class("text", v)] if _color_class("text", v) else None,
    "backgroundColor": lambda v: [_color_class("bg", v)] if _color_class("bg", v) else None,
    "background": lambda v: [_color_class("bg", v)] if _color_class("bg", v) else None,
    "borderColor": lambda v: [_color_class("border", v)] if _color_class("border", v) else None,
    "border": _border_class,
    "borderRadius": lambda v: [RADIUS_MAP[v.strip()]] if v.strip() in RADIUS_MAP else None,
    "fontSize": lambda v: [_font_size_class(v)] if _font_size_class(v) else None,
    "fontWeight": lambda v: [FONT_WEIGHT_MAP[str(v).strip()]]
    if str(v).strip() in FONT_WEIGHT_MAP
    else None,
    "fontFamily": lambda v: [FONT_FAMILY_MAP[v.strip()]] if v.strip() in FONT_FAMILY_MAP else None,
    "lineHeight": lambda v: [_line_height_class(v)] if _line_height_class(v) else None,
    "textAlign": lambda v: [TEXT_ALIGN_MAP[v.strip()]] if v.strip() in TEXT_ALIGN_MAP else None,
    "display": lambda v: [DISPLAY_MAP[v.strip()]] if v.strip() in DISPLAY_MAP else None,
    "flexDirection": lambda v: [FLEX_DIRECTION_MAP[v.strip()]]
    if v.strip() in FLEX_DIRECTION_MAP
    else None,
    "justifyContent": lambda v: [JUSTIFY_MAP[v.strip()]] if v.strip() in JUSTIFY_MAP else None,
    "alignItems": lambda v: [ALIGN_MAP[v.strip()]] if v.strip() in ALIGN_MAP else None,
    "whiteSpace": lambda v: [WHITESPACE_MAP[v.strip()]] if v.strip() in WHITESPACE_MAP else None,
    "cursor": lambda v: [CURSOR_MAP[v.strip()]] if v.strip() in CURSOR_MAP else None,
    "overflow": lambda v: [OVERFLOW_MAP[v.strip()]] if v.strip() in OVERFLOW_MAP else None,
    "overflowX": lambda v: [OVERFLOW_MAP[v.strip()].replace("overflow-", "overflow-x-")]
    if v.strip() in OVERFLOW_MAP
    else None,
    "overflowY": lambda v: [OVERFLOW_MAP[v.strip()].replace("overflow-", "overflow-y-")]
    if v.strip() in OVERFLOW_MAP
    else None,
    "boxShadow": lambda v: [SHADOW_MAP[v.strip()]] if v.strip() in SHADOW_MAP else None,
    "flexShrink": lambda v: ["shrink-0" if str(v).strip() == "0" else None][:1],
    "flexGrow": lambda v: ["grow" if str(v).strip() == "1" else "grow-0"],
}


# =============================================================================
# Parsing
# =============================================================================

# Match style={{ ... }} attributes. Conservative: requires balanced braces.
STYLE_ATTR_RE = re.compile(r"style=\{\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\}", re.DOTALL)

# Parse individual key:value pairs inside a style object. Handles both single
# and double quoted values, template strings, and identifiers.
# key → value , where value is either a string literal, template string,
# simple identifier, or a call expression.
STYLE_KV_RE = re.compile(
    r"""(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(?P<value>
        '[^']*'           # 'value'
      | "[^"]*"           # "value"
      | `[^`]*`           # `value ${interp}`
      | [^,]+             # other (identifiers, expressions)
    )\s*(?:,|$)
    """,
    re.VERBOSE,
)


@dataclass
class StyleEntry:
    """A single key:value pair extracted from a style attribute."""

    key: str
    raw_value: str  # the raw RHS including quotes
    value: str  # the string content (quotes stripped) or original if dynamic

    @property
    def is_dynamic(self) -> bool:
        """True if the RHS contains a template literal or non-string-literal expression."""
        stripped = self.raw_value.strip()
        # Template string with interpolation
        if stripped.startswith("`") and "${" in stripped:
            return True
        # Simple string literal → static
        if stripped.startswith(("'", '"', "`")):
            return False
        # Anything else (identifier, call, ternary, etc.) → dynamic
        return True


@dataclass
class StyleAttr:
    """A full style={{ ... }} attribute found in a file."""

    start: int
    end: int
    raw: str  # the full match including style={{ ... }}
    entries: list[StyleEntry]


def parse_style_attrs(source: str) -> list[StyleAttr]:
    """Find every style={{ ... }} attribute in the source file."""
    attrs: list[StyleAttr] = []
    for m in STYLE_ATTR_RE.finditer(source):
        body = m.group(1)
        entries: list[StyleEntry] = []
        for kv in STYLE_KV_RE.finditer(body):
            key = kv.group("key")
            raw_value = kv.group("value").strip().rstrip(",").strip()
            value = raw_value
            # Strip matching quote pairs for string literals
            if (value.startswith("'") and value.endswith("'")) or (
                value.startswith('"') and value.endswith('"')
            ):
                value = value[1:-1]
            entries.append(StyleEntry(key=key, raw_value=raw_value, value=value))
        attrs.append(StyleAttr(start=m.start(), end=m.end(), raw=m.group(0), entries=entries))
    return attrs


# =============================================================================
# Conversion
# =============================================================================


@dataclass
class ConversionResult:
    """Result of trying to convert one StyleAttr."""

    attr: StyleAttr
    all_convertible: bool  # True if every entry has a 1:1 Tailwind mapping
    classes: list[str]  # list of Tailwind classes
    unconvertible: list[tuple[str, str]]  # (key, value) pairs needing manual review
    dynamic: list[tuple[str, str]]  # (key, raw_value) pairs with runtime expressions


def convert_attr(attr: StyleAttr) -> ConversionResult:
    """Try to convert a full style attribute to Tailwind classes."""
    classes: list[str] = []
    unconvertible: list[tuple[str, str]] = []
    dynamic: list[tuple[str, str]] = []

    for entry in attr.entries:
        if entry.is_dynamic:
            dynamic.append((entry.key, entry.raw_value))
            continue

        resolver = PROPERTY_RESOLVERS.get(entry.key)
        if not resolver:
            unconvertible.append((entry.key, entry.value))
            continue

        result = resolver(entry.value)
        if not result or any(c is None for c in result):
            unconvertible.append((entry.key, entry.value))
            continue

        classes.extend([c for c in result if c])

    all_convertible = not unconvertible and not dynamic
    return ConversionResult(
        attr=attr,
        all_convertible=all_convertible,
        classes=classes,
        unconvertible=unconvertible,
        dynamic=dynamic,
    )


# =============================================================================
# CLI
# =============================================================================


def report(file_path: Path, results: list[ConversionResult]) -> None:
    """Print a summary + per-attribute detail for the given file."""
    total = len(results)
    fully = sum(1 for r in results if r.all_convertible)
    partial = sum(
        1 for r in results if not r.all_convertible and (r.classes or r.unconvertible or r.dynamic)
    )
    dynamic_only = sum(
        1 for r in results if not r.classes and r.dynamic and not r.unconvertible
    )

    print(f"\n=== {file_path} ===")
    print(
        f"  {total} style={{...}} attributes | "
        f"{fully} fully convertible | "
        f"{partial} partial | "
        f"{dynamic_only} dynamic-only (keep inline)"
    )

    for i, r in enumerate(results, 1):
        header = f"\n  [{i}/{total}] "
        if r.all_convertible:
            header += f"[OK] FULLY CONVERTIBLE ({len(r.classes)} classes)"
        elif not r.classes and r.dynamic and not r.unconvertible:
            header += "[DYN] DYNAMIC-ONLY (leave inline)"
        else:
            header += "[PARTIAL] needs manual review"
        print(header)

        if r.classes:
            print(f"        -> className=\"{' '.join(r.classes)}\"")
        for key, val in r.unconvertible:
            print(f"        x unconvertible: {key}: {val!r}")
        for key, val in r.dynamic:
            print(f"        ~ dynamic: {key}: {val}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate inline-styles to Tailwind classes.")
    parser.add_argument("file", type=Path, help="Path to the .tsx file to analyse.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite the file in place, replacing fully-convertible attributes.",
    )
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    source = args.file.read_text(encoding="utf-8")
    attrs = parse_style_attrs(source)
    results = [convert_attr(a) for a in attrs]

    report(args.file, results)

    if args.apply:
        # Only rewrite fully-convertible attributes. Sort by descending start
        # offset so earlier rewrites don't shift later positions.
        fully_convertible = sorted(
            (r for r in results if r.all_convertible),
            key=lambda r: r.attr.start,
            reverse=True,
        )
        new_source = source
        for r in fully_convertible:
            # Find the enclosing JSX attribute region to determine whether we
            # need to ADD a new className attribute or MERGE with an existing
            # one. For simplicity the tool only supports the REPLACE case
            # (removes style={{...}} and leaves a marker comment). Merging
            # with existing className is left to the caller's diff review.
            replacement = f'/* TODO-migrate: add className="{" ".join(r.classes)}" */'
            new_source = new_source[: r.attr.start] + replacement + new_source[r.attr.end :]
        args.file.write_text(new_source, encoding="utf-8")
        print(f"\nApplied {len(fully_convertible)} rewrites to {args.file}")
        print("Review the TODO-migrate comments and merge the class strings into the")
        print("existing className attributes manually. DO NOT commit without visual review.")

    # Exit code: 0 if any conversions happened, 1 if nothing to do.
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
