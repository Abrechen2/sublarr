"""ffsubsync's voice-activity fallback loads without pkg_resources.

setuptools was pinned <81 for years because webrtcvad imported pkg_resources
at module level (84aac466). webrtcvad-wheels 2.0.14 reads its version through
importlib.metadata, so 1.17.2 lifted the pin; this keeps that true.
"""

import importlib
import sys

import pytest

pytest.importorskip("webrtcvad")


def test_webrtcvad_imports_with_pkg_resources_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pkg_resources", None)
    monkeypatch.delitem(sys.modules, "webrtcvad", raising=False)

    webrtcvad = importlib.import_module("webrtcvad")

    assert webrtcvad.Vad(2).is_speech(b"\x00" * 320, 16000) is False
