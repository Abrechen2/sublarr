from sensitive_keys import is_sensitive_key


def test_provider_api_keys_are_sensitive():
    assert is_sensitive_key("opensubtitles_api_key")
    assert is_sensitive_key("subdl_api_key")
    assert is_sensitive_key("deepl_api_key")


def test_passwords_and_tokens_are_sensitive():
    assert is_sensitive_key("addic7ed_password")
    assert is_sensitive_key("github_token")


def test_bare_api_key_is_sensitive():
    assert is_sensitive_key("api_key")


def test_non_secret_keys_are_not_sensitive():
    assert not is_sensitive_key("ui_auth_enabled")
    assert not is_sensitive_key("wanted_search_interval")


def test_master_key_source_is_excluded():
    # ui_session_secret is the SECRET_KEY source stored in the DB; encrypting
    # it would create a circular dependency and defeat the threat model.
    assert not is_sensitive_key("ui_session_secret")


def test_password_hash_is_excluded():
    # already a bcrypt hash, not reversible plaintext
    assert not is_sensitive_key("ui_password_hash")
