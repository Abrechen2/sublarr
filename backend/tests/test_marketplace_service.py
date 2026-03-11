"""Tests for SHA256 integrity verification in the marketplace service."""

import hashlib
import io
import zipfile

import pytest
from unittest.mock import patch, MagicMock


def make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("provider.py", "class P: pass")
    return buf.getvalue()


def test_sha256_passes_on_match():
    from services.marketplace import verify_zip_sha256

    data = make_zip_bytes()
    expected = hashlib.sha256(data).hexdigest()
    assert verify_zip_sha256(data, expected) is True


def test_sha256_fails_on_mismatch():
    from services.marketplace import verify_zip_sha256

    data = make_zip_bytes()
    assert verify_zip_sha256(data, "wrong") is False


def test_sha256_skipped_when_empty():
    from services.marketplace import verify_zip_sha256

    assert verify_zip_sha256(b"anything", "") is True


def test_sha256_case_insensitive():
    from services.marketplace import verify_zip_sha256

    data = make_zip_bytes()
    expected = hashlib.sha256(data).hexdigest().upper()
    assert verify_zip_sha256(data, expected) is True


def test_install_raises_on_sha256_mismatch(tmp_path):
    from services.marketplace import PluginMarketplace

    data = make_zip_bytes()
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.content = data
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        marketplace = PluginMarketplace()
        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            marketplace.install_plugin_from_zip(
                plugin_name="test",
                zip_url="https://example.com/plugin.zip",
                expected_sha256="0" * 64,
                plugins_dir=str(tmp_path),
            )


def test_install_succeeds_on_correct_sha256(tmp_path):
    from services.marketplace import PluginMarketplace

    data = make_zip_bytes()
    correct_sha = hashlib.sha256(data).hexdigest()
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.content = data
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        with patch("services.marketplace.safe_zip_extract"):
            marketplace = PluginMarketplace()
            result = marketplace.install_plugin_from_zip(
                plugin_name="test",
                zip_url="https://example.com/plugin.zip",
                expected_sha256=correct_sha,
                plugins_dir=str(tmp_path),
            )
    assert result["status"] == "installed"
    assert "test" in result["path"]


def test_install_skips_sha256_when_empty(tmp_path):
    from services.marketplace import PluginMarketplace

    data = make_zip_bytes()
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.content = data
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        with patch("services.marketplace.safe_zip_extract"):
            marketplace = PluginMarketplace()
            result = marketplace.install_plugin_from_zip(
                plugin_name="test",
                zip_url="https://example.com/plugin.zip",
                expected_sha256="",
                plugins_dir=str(tmp_path),
            )
    assert result["status"] == "installed"
