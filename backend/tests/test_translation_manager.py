"""TranslationManager wiring tests (Phase A1)."""

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


def _make_fake_backend(name: str):
    """Build a minimal concrete TranslationBackend subclass with the given name."""
    from translation.base import TranslationBackend, TranslationResult

    class FakeBackend(TranslationBackend):
        display_name = "Fake"
        config_fields: list[dict] = []
        supports_glossary = False
        supports_batch = True
        max_batch_size = 10

        def translate_batch(
            self,
            lines,
            source_lang,
            target_lang,
            glossary_entries=None,
            series_context=None,
        ):
            return TranslationResult(translated_lines=list(lines), backend_name=self.name)

        def health_check(self):
            return (True, "ok")

        def get_config_fields(self):
            return []

    FakeBackend.name = name
    return FakeBackend


def test_register_backend_registers_with_concurrency(app):
    """register_backend must also register the backend with BackendConcurrency."""
    from translation import TranslationManager
    from translation.concurrency import get_concurrency, reset_for_tests

    FakeBackend = _make_fake_backend("my_fake")

    reset_for_tests()
    with app.app_context():
        mgr = TranslationManager()
        mgr.register_backend(FakeBackend)
        assert get_concurrency().get_limit("my_fake") == 3  # default


def test_config_override_honored(app):
    """If config has translation_concurrency_<name>, it's applied."""
    from db.config import save_config_entry
    from translation import TranslationManager
    from translation.concurrency import get_concurrency, reset_for_tests

    FakeBackend = _make_fake_backend("my_fake2")

    with app.app_context():
        save_config_entry("translation_concurrency_my_fake2", "7")

        reset_for_tests()
        mgr = TranslationManager()
        mgr.register_backend(FakeBackend)
        assert get_concurrency().get_limit("my_fake2") == 7
