"""Bounded, lossless ASS event lexer shared by selection and sanitization.

Drawing-state parsing follows libass 0.17.3 ass_parse.c argument boundaries.
Only drawing state is interpreted; other overrides retain their exact spelling.
Reference: https://github.com/libass/libass/blob/0.17.3/libass/ass_parse.c
Validated against ffmpeg/libass pixels; this is not a general ASS validator.
"""

import re
from dataclasses import dataclass

MAX_EVENT = 131072
MAX_TAGS = 4096
MAX_TRANSFORMS = 32
INTEGER = re.compile(r"[ \t\r\n\v\f]*([+-]?)([0-9]+)")
LAYOUT = re.compile(r"\\[Nnh]")


class ASSNeedsReviewError(ValueError):
    """The event or model output cannot safely be rewritten."""


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    raw: str
    kind: str
    drawing: bool
    group: int | None


def _positive(arg):
    # strtoll's ASCII whitespace/sign/digits; clamping cannot change positivity.
    match = INTEGER.match(arg)
    return bool(match and match[1] != "-" and any(c != "0" for c in match[2]))


def _state(block, current, budget, depth=0):
    if depth > MAX_TRANSFORMS:
        raise ASSNeedsReviewError("transform nesting limit")
    p = 0
    end = len(block)
    while p < end:
        slash = block.find("\\", p)
        if slash < 0:
            break
        budget[0] -= 1
        if budget[0] < 0:
            raise ASSNeedsReviewError("tag budget exceeded")
        p = slash + 1
        while p < end and block[p] in " \t":
            p += 1
        q = p
        while q < end and block[q] not in "(\\":
            q += 1
        if q == p:
            continue
        name = block[p:q]
        args = []
        has_backslash = False

        def push(a, b):
            part = block[a:b].rstrip(" \t")
            if part and len(args) < 8:
                args.append(part)

        if q < end and block[q] == "(":
            q += 1
            while True:
                while q < end and block[q] in " \t":
                    q += 1
                r = q
                while r < end and block[r] not in ",\\)":
                    r += 1
                if r < end and block[r] == ",":
                    push(q, r)
                    q = r + 1
                    continue
                if r < end and block[r] == "\\":
                    has_backslash = True
                    close = block.find(")", r)
                    r = end if close < 0 else close
                push(q, r)
                q = min(r + 1, end)
                break

        # Prefix precedence matters: pos and pbo are NOT drawing switches.
        if name.startswith("p") and not name.startswith(("pos", "pbo")):
            remainder = name[1:].rstrip(" \t")
            if remainder and len(args) < 8:
                args.append(remainder)
            current = _positive(args[0] if args else "")
        elif name.startswith("t") and has_backslash and 1 <= len(args) <= 4:
            # Drawing mode is set directly even inside timed transforms.
            current = _state(args[-1], current, budget, depth + 1)
        p = q
    return current


def lex(text: str) -> tuple[list[Token], set[int]]:
    if len(text) > MAX_EVENT:
        raise ASSNeedsReviewError("event size limit")
    if "\x00" in text or "\n" in text or "\r" in text:
        raise ASSNeedsReviewError("invalid physical event boundary")
    tokens = []
    drawing = False
    group = None
    next_group = 0
    closed = set()
    pos = 0
    budget = [MAX_TAGS]
    while pos < len(text):
        if text[pos] == "{":
            end = text.find("}", pos + 1)
            if end < 0:
                raise ASSNeedsReviewError("unclosed override block")
            raw = text[pos : end + 1]
            new_drawing = _state(raw[1:-1], drawing, budget)
            if new_drawing and not drawing:
                group = next_group
                next_group += 1
            elif drawing and not new_drawing:
                closed.add(group)
            tokens.append(Token(pos, end + 1, raw, "override", new_drawing, group))
            drawing = new_drawing
            if not drawing:
                group = None
            pos = end + 1
        else:
            end = text.find("{", pos)
            if end < 0:
                end = len(text)
            tokens.append(Token(pos, end, text[pos:end], "content", drawing, group))
            pos = end
    return tokens, closed


def remove_closed_geometry(text):
    """Optional policy: remove geometry content only, retain ALL original tags.

    Keep drawing switches too: empty p1...p0 spans are harmless, while rewriting
    nested overrides can change their meaning. Unclosed drawings are preserved.
    """
    tokens, closed = lex(text)
    return "".join(
        t.raw for t in tokens if not (t.kind == "content" and t.drawing and t.group in closed)
    )


_HARD = "\\N"
_SOFT = "\\n"
_LONE_SOFT = re.compile(r"(?<!\\)\\n")


def align_break_spelling(source: str, translated: str) -> str:
    """Spell the model's line breaks the way the source spells them.

    Models answer a ``\\N`` with ``\\n`` or with a real newline all the time:
    of prod's 8 005 memory entries with a break in the four days to
    2026-09-24, 4 811 (60 %) came back as ``\\n``. That is the model re-spelling
    the break, not changing the layout, so it is repaired here instead of being
    rejected. Where the source mixes both kinds the model's choice is kept,
    because which of its breaks answers which source break would be a guess.
    A break the source never had becomes a space, the rule
    ``translation.llm_utils.strip_invented_hard_breaks`` already applies to LLM
    answers; repeating it here covers every other backend too.
    """
    if not isinstance(translated, str):
        return translated
    has_hard = _HARD in source
    has_soft = _LONE_SOFT.search(source) is not None
    wanted = _SOFT if has_soft and not has_hard else _HARD
    aligned = translated.replace("\r\n", "\n").replace("\r", "\n").replace("\n", wanted)
    if not has_hard and not has_soft:
        aligned = _LONE_SOFT.sub(" ", aligned.replace(_HARD, " "))
    elif has_hard and not has_soft:
        aligned = _LONE_SOFT.sub(lambda _m: _HARD, aligned)
    elif has_soft and not has_hard:
        aligned = aligned.replace(_HARD, _SOFT)
    return re.sub(r"  +", " ", aligned).strip()


def validate_translation(_source: str, translated: str) -> None:
    """Reject a model answer that would put new ASS syntax into the output.

    Line breaks are not compared with the source: a model that reflows a long
    German sentence onto one line fewer or more changes nothing but the wrap,
    and 10 % of prod's multi-line answers differ in count. Rejecting those
    would reject almost every multi-line file. The source stays in the
    signature so callers pass the pair they align first (``align_break_spelling``).
    """
    if not isinstance(translated, str) or not translated.strip():
        raise ASSNeedsReviewError("empty or non-string ASS translation")
    if len(translated) > MAX_EVENT:
        raise ASSNeedsReviewError("translated event size limit")
    if any(char in translated for char in "{}\x00\r\n"):
        raise ASSNeedsReviewError("model introduced ASS or physical event syntax")
    if "\\" in LAYOUT.sub("", translated):
        raise ASSNeedsReviewError("model introduced an unsupported ASS escape")
