"""The set of config keys a config-import or a full-restore may never set.

This used to be two hand-written lists, one in ``routes/config/io.py`` and one
in ``routes/system/backup_full.py``. Both named ``opensubtitles_password`` but
neither had been extended when later providers added their own credentials, so
an import payload could plant them. These tests pin the derivation that
replaced the lists, and the properties that make it drift-proof.
"""

from routes.config.io import _secret_import_keys
from sensitive_keys import is_sensitive_key

# Exactly what the two hand-written lists contained before they were derived.
# Nothing they protected may fall out of the derived set.
_LEGACY_IMPORT_LIST = {
    "api_key",
    "sonarr_api_key",
    "radarr_api_key",
    "jellyfin_api_key",
    "opensubtitles_api_key",
    "opensubtitles_password",
    "jimaku_api_key",
    "subdl_api_key",
    "tmdb_api_key",
    "tvdb_api_key",
    "tvdb_pin",
    "deepl_api_key",
    "notification_urls_json",
    "sonarr_instances_json",
    "radarr_instances_json",
    "media_servers_json",
}


class TestDerivedBlocklistLosesNothing:
    def test_covers_every_key_the_hand_written_list_did(self):
        assert _LEGACY_IMPORT_LIST - _secret_import_keys() == set()

    def test_deepl_survives_although_it_is_not_a_settings_field(self):
        """deepl_api_key lives only in config_entries / API_KEY_REGISTRY.

        Deriving from the settings models alone silently dropped it.
        """
        from config_settings import BootSettings, UISettings

        assert "deepl_api_key" not in (
            set(BootSettings.model_fields) | set(UISettings.model_fields)
        )
        assert "deepl_api_key" in _secret_import_keys()


class TestDerivedBlocklistClosesTheDrift:
    def test_provider_passwords_added_after_the_list_are_covered(self):
        blocked = _secret_import_keys()
        for key in ("titlovi_password", "addic7ed_password", "turkcealtyazi_password"):
            assert key in blocked, f"{key} must not be settable through an import"

    def test_every_sensitive_settings_field_is_blocked(self):
        """The property that makes the set drift-proof: a provider added
        tomorrow is covered the day its field lands, with no list to edit."""
        from config_settings import BootSettings, UISettings

        blocked = _secret_import_keys()
        sensitive_fields = {
            name
            for name in (set(BootSettings.model_fields) | set(UISettings.model_fields))
            if is_sensitive_key(name)
        }
        assert sensitive_fields <= blocked
        assert sensitive_fields, "guard against the classifier silently matching nothing"

    def test_non_secret_settings_stay_importable(self):
        """Over-blocking would quietly break config import instead of a
        credential leak — check a few ordinary keys are still allowed."""
        blocked = _secret_import_keys()
        for key in ("ollama_url", "log_level", "port"):
            assert key not in blocked


class TestExcludedKeysAreNotBlocked:
    def test_session_secret_and_password_hash_follow_the_classifier(self):
        """Both are deliberately excluded from is_sensitive_key (see
        sensitive_keys module docstring) and must not be re-added here."""
        blocked = _secret_import_keys()
        assert "ui_session_secret" not in blocked
        assert "ui_password_hash" not in blocked


class TestBothCallSitesShareOneSource:
    def test_restore_path_uses_the_same_helper(self):
        """The restore path had the shorter of the two lists — it did not even
        cover deepl or the JSON blobs. It must not diverge again."""
        import routes.system.backup_full as backup_full

        assert backup_full._secret_import_keys is _secret_import_keys
