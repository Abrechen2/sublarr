"""Fonts are served by Sublarr, never by Google (code check 2026-11-05, #76).

Loading Inter and JetBrains Mono from fonts.googleapis.com sent every
visitor's IP address to Google, and the CSP allowed it.
"""

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
GOOGLE_FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")


def test_the_csp_allows_no_font_cdn(client):
    csp = client.get("/api/v1/health").headers.get("Content-Security-Policy", "")
    assert csp, "the CSP header must be set"
    for host in GOOGLE_FONT_HOSTS:
        assert host not in csp


@pytest.mark.parametrize("rel", ["index.html", "src/index.css"])
def test_the_frontend_loads_no_font_cdn(rel):
    path = FRONTEND / rel
    if not path.exists():
        pytest.skip("frontend sources not present")
    text = path.read_text(encoding="utf-8")
    for host in GOOGLE_FONT_HOSTS:
        assert host not in text
