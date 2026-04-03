"""Unit tests for anidb_sync module — token parsing, XML processing, and route."""

import pytest

from anidb_sync import _parse_mapping_token, _process_xml, sync_state

# ---------------------------------------------------------------------------
# _parse_mapping_token tests
# ---------------------------------------------------------------------------


def test_parse_token_valid():
    result = _parse_mapping_token("1-2")
    assert result == (1, 2)


def test_parse_token_with_spaces():
    result = _parse_mapping_token("  3-7  ")
    assert result == (3, 7)


@pytest.mark.parametrize("token", ["bad", "1-2-3", ""])
def test_parse_token_malformed_returns_none(token):
    assert _parse_mapping_token(token) is None


def test_parse_token_non_numeric_returns_none():
    assert _parse_mapping_token("a-b") is None


def test_parse_token_zero_values():
    result = _parse_mapping_token("0-0")
    assert result == (0, 0)


# ---------------------------------------------------------------------------
# _process_xml tests
# ---------------------------------------------------------------------------

VALID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<anime-list>
  <anime tvdbid="12345">
    <mapping-list>
      <mapping tvdbseason="1">1-1;2-2;3-3;</mapping>
    </mapping-list>
  </anime>
</anime-list>
"""

MISSING_TVDBID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<anime-list>
  <anime tvdbid="">
    <mapping-list>
      <mapping tvdbseason="1">1-1;</mapping>
    </mapping-list>
  </anime>
</anime-list>
"""


def test_process_xml_valid(app_ctx):
    """Valid XML with mappings should upsert at least one mapping."""
    result = _process_xml(VALID_XML, app_ctx)
    assert result["error"] is None
    assert result["mappings_upserted"] >= 1
    assert result["series_processed"] >= 1


def test_process_xml_malformed_returns_error(app_ctx):
    """Malformed XML should return a dict with an error key."""
    result = _process_xml(b"<<not xml>>", app_ctx)
    assert result["error"] is not None
    assert "XML" in result["error"] or "parse" in result["error"].lower()


def test_process_xml_skips_missing_tvdbid(app_ctx):
    """Anime element with empty tvdbid should increment skipped counter."""
    result = _process_xml(MISSING_TVDBID_XML, app_ctx)
    assert result["error"] is None
    assert result["skipped"] >= 1


# ---------------------------------------------------------------------------
# Route: POST /api/v1/anidb-mapping/refresh → 409 when already running
# ---------------------------------------------------------------------------


def test_refresh_returns_409_when_running(client, monkeypatch):
    """If sync is already running, the refresh endpoint must return 409."""
    import anidb_sync

    monkeypatch.setitem(anidb_sync.sync_state, "running", True)
    response = client.post("/api/v1/anidb-mapping/refresh")
    assert response.status_code == 409
    data = response.get_json()
    assert data["success"] is False
    # Reset so other tests are not affected
    monkeypatch.setitem(anidb_sync.sync_state, "running", False)
