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


# Bleach, copied verbatim from anime-list.xml (tvdbid 74796, anidbid 2369).
# Every one of these mapping elements has EMPTY text: the episode pairs live
# in the start/end/offset attributes. Issue #205 — the parser read only the
# text, so a series mapped this way produced no rows at all and absolute-order
# search fell back to plain S/E numbering.
RANGE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<anime-list>
  <anime anidbid="2369" tvdbid="74796" defaulttvdbseason="a">
    <mapping-list>
      <mapping anidbseason="0" tvdbseason="0">;2-99;3-2;4-0;</mapping>
      <mapping anidbseason="1" tvdbseason="1" start="1" end="20"></mapping>
      <mapping anidbseason="1" tvdbseason="2" start="21" end="41" offset="-20"></mapping>
      <mapping anidbseason="1" tvdbseason="3" start="42" end="63" offset="-41"></mapping>
    </mapping-list>
  </anime>
</anime-list>
"""


def _mapping_for(season, episode, tvdb_id=74796):
    from db.repositories.anidb import AnidbRepository

    return AnidbRepository().get_anidb_absolute(tvdb_id=tvdb_id, season=season, episode=episode)


def test_process_xml_expands_range_mapping(app_ctx):
    """A mapping carrying start/end/offset must produce one row per episode.

    Issue #205: Bleach S02E01 has to resolve to AniDB absolute episode 21.
    """
    result = _process_xml(RANGE_XML, app_ctx)
    assert result["error"] is None

    with app_ctx.app_context():
        assert _mapping_for(2, 1) == 21
        assert _mapping_for(2, 21) == 41
        # offset defaults to 0 when the attribute is absent
        assert _mapping_for(1, 1) == 1
        assert _mapping_for(1, 20) == 20
        assert _mapping_for(3, 1) == 42


def test_process_xml_range_and_explicit_tokens_both_apply(app_ctx):
    """Text tokens next to a range are not lost — the two are additive."""
    both = b"""<?xml version="1.0" encoding="UTF-8"?>
<anime-list>
  <anime tvdbid="4242">
    <mapping-list>
      <mapping tvdbseason="1" start="5" end="6" offset="-4">;9-7;</mapping>
    </mapping-list>
  </anime>
</anime-list>
"""
    result = _process_xml(both, app_ctx)
    assert result["error"] is None
    with app_ctx.app_context():
        assert _mapping_for(1, 1, tvdb_id=4242) == 5
        assert _mapping_for(1, 2, tvdb_id=4242) == 6
        assert _mapping_for(1, 7, tvdb_id=4242) == 9


def test_process_xml_range_rejects_absurd_and_negative_results(app_ctx):
    """A malformed range must not flood the table or write episode <= 0."""
    bad = b"""<?xml version="1.0" encoding="UTF-8"?>
<anime-list>
  <anime tvdbid="4243">
    <mapping-list>
      <mapping tvdbseason="1" start="1" end="900000"></mapping>
    </mapping-list>
  </anime>
  <anime tvdbid="4244">
    <mapping-list>
      <mapping tvdbseason="1" start="1" end="3" offset="-10"></mapping>
    </mapping-list>
  </anime>
  <anime tvdbid="4245">
    <mapping-list>
      <mapping tvdbseason="1" start="9" end="2"></mapping>
    </mapping-list>
  </anime>
</anime-list>
"""
    result = _process_xml(bad, app_ctx)
    assert result["error"] is None
    assert result["mappings_upserted"] == 0
    with app_ctx.app_context():
        assert _mapping_for(1, 1, tvdb_id=4243) is None
        assert _mapping_for(1, 1, tvdb_id=4244) is None
        assert _mapping_for(1, 1, tvdb_id=4245) is None


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
