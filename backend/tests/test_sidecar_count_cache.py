"""The sidecar count cache must survive a scan of the whole library.

Prod 2026-11-06 (rc.2): one wanted cleanup reads 9,994 distinct sidecars, the
cache held 8,192 and was cleared outright when full. Every pass therefore
parsed nearly every subtitle again; the cleanup took 172 s instead of 59 s,
and longer on a slow disk. A full cache now drops only its oldest entries.
"""

import pytest

import subtitle_dialogue as sd

ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize\nStyle: Default,Arial,20\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello\n"
)


@pytest.fixture()
def parses(monkeypatch):
    calls = []
    real = sd._parse

    def counting(content):
        calls.append(1)
        return real(content)

    monkeypatch.setattr(sd, "_parse", counting)
    monkeypatch.setattr(sd, "_count_cache", {})
    return calls


def _files(tmp_path, n):
    paths = []
    for i in range(n):
        p = tmp_path / f"ep{i:03d}.de.ass"
        p.write_text(ASS, encoding="utf-8")
        paths.append(str(p))
    return paths


def test_overflow_keeps_the_newest_entries(tmp_path, parses, monkeypatch):
    monkeypatch.setattr(sd, "_COUNT_CACHE_MAX", 8)
    paths = _files(tmp_path, 9)
    for p in paths:
        sd._sidecar_counts(p)
    assert len(parses) == 9
    for p in paths[-6:]:
        sd._sidecar_counts(p)
    assert len(parses) == 9, "a full cache threw away entries it had just filled"


def test_the_cache_holds_a_large_library():
    assert sd._COUNT_CACHE_MAX >= 50_000
