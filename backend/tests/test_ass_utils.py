"""Tests for ass_utils.py — subtitle utilities."""

import pytest
from ass_utils import classify_styles, extract_tags, restore_tags, fix_line_breaks
import pysubs2


def test_classify_styles():
    """Test style classification."""
    subs = pysubs2.SSAFile()
    subs.styles["Default"] = pysubs2.SSAStyle()
    subs.styles["Sign"] = pysubs2.SSAStyle()
    
    event1 = pysubs2.SSAEvent(text="Hello", style="Default")
    event2 = pysubs2.SSAEvent(text="Sign text", style="Sign")
    subs.events = [event1, event2]
    
    dialog, signs = classify_styles(subs)
    assert "Default" in dialog
    assert "Sign" in signs


def test_extract_tags():
    """Test ASS override tag extraction."""
    text = "{\\i1}Hello{\\i0} World"
    clean, tags, orig_len = extract_tags(text)
    assert "Hello" in clean
    assert "World" in clean
    assert len(tags) > 0
    assert orig_len == len(clean)


def test_restore_tags():
    """Test tag restoration."""
    clean = "Hello World"
    tag_info = [(0, "{\\i1}"), (5, "{\\i0}")]
    restored = restore_tags(clean, tag_info, len(clean))
    assert "{\\i1}" in restored
    assert "{\\i0}" in restored


def test_fix_line_breaks():
    """Test line break fixing."""
    text = "Line 1\\nLine 2"
    fixed = fix_line_breaks(text)
    assert "\\N" in fixed
    assert "\\n" not in fixed or fixed.count("\\n") < text.count("\\n")
