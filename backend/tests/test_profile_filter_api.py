"""Tests that profile filter fields round-trip through the repository layer."""
import json
from unittest.mock import MagicMock, patch


def _make_profile_dict(
    must_contain_json="[]",
    must_not_contain_json="[]",
    cutoff_language="",
    audio_exclude_languages_json="[]",
):
    """Return a dict that mimics what _to_dict() produces from a LanguageProfile row."""
    return {
        "id": 1,
        "name": "Test",
        "source_language": "en",
        "source_language_name": "English",
        "target_languages_json": '["de"]',
        "target_language_names_json": '["German"]',
        "is_default": 0,
        "translation_backend": "ollama",
        "fallback_chain_json": '["ollama"]',
        "forced_preference": "disabled",
        "must_contain_json": must_contain_json,
        "must_not_contain_json": must_not_contain_json,
        "cutoff_language": cutoff_language,
        "audio_exclude_languages_json": audio_exclude_languages_json,
        "created_at": None,
        "updated_at": None,
    }


def _call_row_to_profile(profile_dict: dict) -> dict:
    """Call _row_to_profile by patching _to_dict to return the given dict."""
    from db.repositories.profiles import ProfileRepository

    repo = ProfileRepository.__new__(ProfileRepository)
    fake_row = MagicMock()
    with patch.object(repo, "_to_dict", return_value=profile_dict):
        return repo._row_to_profile(fake_row)


class TestRowToProfileFilterFields:
    def test_must_contain_deserialized(self):
        result = _call_row_to_profile(
            _make_profile_dict(must_contain_json='["BluRay","x265"]')
        )
        assert "must_contain" in result
        assert result["must_contain"] == ["BluRay", "x265"]
        assert "must_contain_json" not in result

    def test_must_not_contain_deserialized(self):
        result = _call_row_to_profile(
            _make_profile_dict(must_not_contain_json='["HDCAM","CAM"]')
        )
        assert "must_not_contain" in result
        assert result["must_not_contain"] == ["HDCAM", "CAM"]
        assert "must_not_contain_json" not in result

    def test_cutoff_language_present(self):
        result = _call_row_to_profile(_make_profile_dict(cutoff_language="de"))
        assert result["cutoff_language"] == "de"

    def test_audio_exclude_deserialized(self):
        result = _call_row_to_profile(
            _make_profile_dict(audio_exclude_languages_json='["de","fr"]')
        )
        assert "audio_exclude_languages" in result
        assert result["audio_exclude_languages"] == ["de", "fr"]
        assert "audio_exclude_languages_json" not in result

    def test_empty_defaults(self):
        result = _call_row_to_profile(_make_profile_dict())
        assert result["must_contain"] == []
        assert result["must_not_contain"] == []
        assert result["cutoff_language"] == ""
        assert result["audio_exclude_languages"] == []

    def test_invalid_json_graceful(self):
        result = _call_row_to_profile(_make_profile_dict(must_contain_json="not-json"))
        assert result["must_contain"] == []

    def test_update_profile_allows_filter_fields(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        mock_profile = MagicMock()
        mock_profile.forced_preference = "disabled"
        repo._local = MagicMock()
        repo._local.batch_mode = False

        mock_session = MagicMock()
        mock_session.get.return_value = mock_profile

        with (
            patch.object(
                type(repo),
                "session",
                new_callable=lambda: property(lambda self: mock_session),
            ),
            patch.object(repo, "_commit"),
            patch.object(repo, "_now", return_value=None),
        ):
            repo.update_profile(
                1,
                must_contain=["BluRay"],
                must_not_contain=["HDCAM"],
                cutoff_language="de",
                audio_exclude_languages=["de"],
            )

        assert mock_profile.must_contain_json == '["BluRay"]'
        assert mock_profile.must_not_contain_json == '["HDCAM"]'
        assert mock_profile.cutoff_language == "de"
        assert mock_profile.audio_exclude_languages_json == '["de"]'
