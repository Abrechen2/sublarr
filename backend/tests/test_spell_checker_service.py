"""Tests for services/spell_checker.py and routes/spell.py.

Mocks pyenchant since it may not be installed in CI.
Covers: SpellChecker class, check_subtitle_file, get_available_dictionaries,
and spell check routes.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: inject a fake enchant module so SpellChecker can be instantiated
# ---------------------------------------------------------------------------


def _make_fake_enchant(check_fn=None):
    """Build a minimal mock of the enchant module."""
    fake = MagicMock()
    fake.DictNotFoundError = type("DictNotFoundError", (Exception,), {})

    mock_dict = MagicMock()
    if check_fn:
        mock_dict.check.side_effect = check_fn
    else:
        mock_dict.check.return_value = True
    mock_dict.suggest.return_value = ["hello", "help"]
    fake.Dict.return_value = mock_dict
    return fake, mock_dict


@pytest.fixture
def fake_enchant():
    """Temporarily install a fake enchant module and enable the flag."""
    fake, mock_dict = _make_fake_enchant()

    # Install fake enchant so `from enchant import ...` works inside lazy imports
    sys.modules["enchant"] = fake

    import services.spell_checker as sc

    original_avail = sc.ENCHANT_AVAILABLE
    sc.ENCHANT_AVAILABLE = True
    sc.enchant = fake  # set module-level reference

    yield fake, mock_dict

    sc.ENCHANT_AVAILABLE = original_avail
    if hasattr(sc, "enchant"):
        delattr(sc, "enchant")
    sys.modules.pop("enchant", None)


# ---------------------------------------------------------------------------
# SpellChecker class
# ---------------------------------------------------------------------------


class TestSpellChecker:
    def test_init_creates_dict(self, fake_enchant):
        from services.spell_checker import SpellChecker

        fake, mock_dict = fake_enchant
        checker = SpellChecker("en_US")
        fake.Dict.assert_called_with("en_US")
        assert checker.language == "en_US"

    def test_init_without_enchant_raises(self):
        import services.spell_checker as sc

        original = sc.ENCHANT_AVAILABLE
        sc.ENCHANT_AVAILABLE = False
        try:
            with pytest.raises(RuntimeError, match="pyenchant not available"):
                sc.SpellChecker("en_US")
        finally:
            sc.ENCHANT_AVAILABLE = original

    def test_init_fallback_language(self, fake_enchant):
        from services.spell_checker import SpellChecker

        fake, _ = fake_enchant
        fake.Dict.side_effect = [
            fake.DictNotFoundError("not found"),
            MagicMock(),
        ]
        checker = SpellChecker("en_US")
        assert checker.language == "en"

    def test_init_no_fallback_raises(self, fake_enchant):
        from services.spell_checker import SpellChecker

        fake, _ = fake_enchant
        fake.Dict.side_effect = fake.DictNotFoundError("not found")
        with pytest.raises(RuntimeError, match="Dictionary not found"):
            SpellChecker("xx_XX")

    def test_add_custom_words(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        checker.add_custom_words(["Naruto", "Sakura", "Jutsu"])
        assert "naruto" in checker.custom_words
        assert "sakura" in checker.custom_words

    def test_check_word_correct(self, fake_enchant):
        from services.spell_checker import SpellChecker

        _, mock_dict = fake_enchant
        mock_dict.check.return_value = True
        checker = SpellChecker("en_US")
        assert checker.check_word("hello") is True

    def test_check_word_misspelled(self, fake_enchant):
        from services.spell_checker import SpellChecker

        _, mock_dict = fake_enchant
        mock_dict.check.return_value = False
        checker = SpellChecker("en_US")
        assert checker.check_word("hllo") is False

    def test_check_word_custom(self, fake_enchant):
        from services.spell_checker import SpellChecker

        _, mock_dict = fake_enchant
        mock_dict.check.return_value = False
        checker = SpellChecker("en_US")
        checker.add_custom_words(["Naruto"])
        assert checker.check_word("Naruto") is True

    def test_check_word_empty(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        assert checker.check_word("") is True

    def test_suggest_returns_limited(self, fake_enchant):
        from services.spell_checker import SpellChecker

        _, mock_dict = fake_enchant
        mock_dict.suggest.return_value = ["a", "b", "c", "d", "e", "f"]
        checker = SpellChecker("en_US")
        assert len(checker.suggest("hllo", max_suggestions=3)) == 3

    def test_suggest_empty_word(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        assert checker.suggest("") == []

    def test_check_text(self, fake_enchant):
        from services.spell_checker import SpellChecker

        _, mock_dict = fake_enchant
        mock_dict.check.side_effect = lambda w: w != "hllo"
        mock_dict.suggest.return_value = ["hello"]
        checker = SpellChecker("en_US")
        errors = checker.check_text("hello hllo world")
        assert len(errors) == 1
        assert errors[0]["word"] == "hllo"

    def test_check_text_enchant_unavailable(self):
        import services.spell_checker as sc

        original = sc.ENCHANT_AVAILABLE
        sc.ENCHANT_AVAILABLE = False
        try:
            checker = sc.SpellChecker.__new__(sc.SpellChecker)
            assert checker.check_text("some text") == []
        finally:
            sc.ENCHANT_AVAILABLE = original


# ---------------------------------------------------------------------------
# _clean_word / _extract_words
# ---------------------------------------------------------------------------


class TestCleanWord:
    def test_clean_word_punctuation(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        assert checker._clean_word('"hello"') == "hello"
        assert checker._clean_word("hello!") == "hello"
        assert checker._clean_word("(world)") == "world"

    def test_clean_word_ass_tags(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        # ASS tags mid-word are stripped by regex
        assert checker._clean_word("hel{\\an8}lo") == "hello"
        # Leading brace gets stripped by punctuation strip first, leaving residue
        assert checker._clean_word("{\\an8}hello") == "an8hello"

    def test_clean_word_html_tags(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        assert checker._clean_word("<b>bold</b>") == "bold"

    def test_extract_words_skips_non_alpha(self, fake_enchant):
        from services.spell_checker import SpellChecker

        checker = SpellChecker("en_US")
        words = checker._extract_words("hello 123 world")
        word_texts = [w[0] for w in words]
        assert "hello" in word_texts
        assert "world" in word_texts
        assert "123" not in word_texts


# ---------------------------------------------------------------------------
# check_subtitle_file
# ---------------------------------------------------------------------------


class TestCheckSubtitleFile:
    def test_enchant_unavailable(self):
        import services.spell_checker as sc

        original = sc.ENCHANT_AVAILABLE
        sc.ENCHANT_AVAILABLE = False
        try:
            result = sc.check_subtitle_file("/some/file.srt")
            assert result["errors"] == []
            assert "not available" in result.get("error", "")
        finally:
            sc.ENCHANT_AVAILABLE = original

    def test_nonexistent_file(self, fake_enchant):
        from services.spell_checker import check_subtitle_file

        result = check_subtitle_file("/nonexistent/path.srt")
        assert "error" in result or result["errors"] == []


# ---------------------------------------------------------------------------
# get_available_dictionaries
# ---------------------------------------------------------------------------


class TestGetAvailableDictionaries:
    def test_enchant_unavailable(self):
        import services.spell_checker as sc

        original = sc.ENCHANT_AVAILABLE
        sc.ENCHANT_AVAILABLE = False
        try:
            assert sc.get_available_dictionaries() == []
        finally:
            sc.ENCHANT_AVAILABLE = original

    def test_returns_language_list(self, fake_enchant):
        from services.spell_checker import get_available_dictionaries

        fake, _ = fake_enchant
        mock_broker = MagicMock()
        mock_broker.list_dicts.return_value = [
            ("en_US", "provider1"),
            ("de_DE", "provider2"),
        ]
        fake.Broker.return_value = mock_broker
        assert get_available_dictionaries() == ["en_US", "de_DE"]

    def test_broker_error_returns_empty(self, fake_enchant):
        from services.spell_checker import get_available_dictionaries

        fake, _ = fake_enchant
        fake.Broker.side_effect = Exception("broker error")
        assert get_available_dictionaries() == []


# ---------------------------------------------------------------------------
# Routes — /spell/check, /spell/dictionaries
# ---------------------------------------------------------------------------


class TestSpellRoutes:
    def test_spell_check_no_input(self, client):
        resp = client.post("/api/v1/spell/check", json={})
        assert resp.status_code == 400
        assert "required" in resp.get_json()["error"]

    def test_spell_check_file_not_found(self, client):
        resp = client.post(
            "/api/v1/spell/check",
            json={"file_path": os.path.join(os.environ.get("SUBLARR_MEDIA_PATH", "/tmp"), "nonexistent.srt")},
        )
        assert resp.status_code == 404

    @patch("routes.spell.is_safe_path", return_value=False)
    def test_spell_check_path_traversal(self, _mock, client):
        resp = client.post(
            "/api/v1/spell/check",
            json={"file_path": "/etc/passwd"},
        )
        assert resp.status_code == 403

    def test_spell_check_content_no_enchant(self, client):
        """Content check without enchant -> 200 with empty result."""
        import services.spell_checker as sc

        original = sc.ENCHANT_AVAILABLE
        sc.ENCHANT_AVAILABLE = False
        try:
            resp = client.post(
                "/api/v1/spell/check",
                json={"content": "hello world"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert "not available" in data.get("error", "")
        finally:
            sc.ENCHANT_AVAILABLE = original

    def test_dictionaries_endpoint(self, client):
        resp = client.get("/api/v1/spell/dictionaries")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dictionaries" in data
        assert isinstance(data["dictionaries"], list)


import os
