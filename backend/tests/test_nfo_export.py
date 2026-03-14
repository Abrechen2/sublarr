"""Tests for nfo_export.py — XML sidecar writing."""
import os
import xml.etree.ElementTree as ET
import pytest
import nfo_export


def test_write_nfo_creates_file(tmp_path):
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")
    nfo_export.write_nfo(str(sub), {"provider": "OpenSubtitles", "score": 720, "source_language": "en", "target_language": "de"})
    nfo = tmp_path / "ep01.de.ass.nfo"
    assert nfo.exists()


def test_write_nfo_xml_content(tmp_path):
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")
    nfo_export.write_nfo(str(sub), {
        "provider": "OpenSubtitles",
        "score": 720,
        "source_language": "en",
        "target_language": "de",
        "translation_backend": "gpt-4o-mini",
        "bleu_score": 0.41,
        "downloaded_at": "2026-03-14T11:30:00",
    })
    tree = ET.parse(str(tmp_path / "ep01.de.ass.nfo"))
    root = tree.getroot()
    assert root.tag == "subtitle"
    assert root.findtext("provider") == "OpenSubtitles"
    assert root.findtext("score") == "720"
    assert root.findtext("target_language") == "de"
    assert root.findtext("translation_backend") == "gpt-4o-mini"


def test_write_nfo_missing_fields_writes_empty_elements(tmp_path):
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")
    nfo_export.write_nfo(str(sub), {})
    tree = ET.parse(str(tmp_path / "ep01.de.ass.nfo"))
    root = tree.getroot()
    assert root.findtext("provider") == ""
    assert root.findtext("score") == ""


def test_write_nfo_error_does_not_raise(tmp_path):
    # Non-existent directory — should log but not raise
    nfo_export.write_nfo("/nonexistent/dir/ep01.de.ass", {"provider": "X"})


def test_maybe_write_nfo_skips_when_disabled(tmp_path, monkeypatch):
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")
    monkeypatch.setattr(nfo_export, "_is_enabled", lambda: False)
    nfo_export.maybe_write_nfo(str(sub), {})
    assert not (tmp_path / "ep01.de.ass.nfo").exists()


def test_maybe_write_nfo_writes_when_enabled(tmp_path, monkeypatch):
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")
    monkeypatch.setattr(nfo_export, "_is_enabled", lambda: True)
    nfo_export.maybe_write_nfo(str(sub), {"provider": "Test"})
    assert (tmp_path / "ep01.de.ass.nfo").exists()
