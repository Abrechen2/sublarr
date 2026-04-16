from unittest.mock import MagicMock

from providers.opensubtitles import OpenSubtitlesProvider


def test_detects_free_tier_from_user_info_response():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "Sub leecher", "vip": False},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "free"


def test_detects_vip_tier():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "VIP member", "vip": True},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "vip"


def test_defaults_to_free_on_failure():
    fake_session = MagicMock()
    fake_session.get.side_effect = Exception("network")
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "free"


def test_detect_tier_caches_result():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "VIP member", "vip": True},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "vip"
    assert p.detect_tier() == "vip"  # second call uses cache
    assert p.detect_tier() == "vip"
    assert fake_session.get.call_count == 1


def test_detect_tier_force_refresh_bypasses_cache():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "Sub leecher", "vip": False},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    p.detect_tier()
    p.detect_tier(force=True)
    assert fake_session.get.call_count == 2
