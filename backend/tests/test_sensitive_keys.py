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


def test_namespaced_keys_are_not_sensitive():
    # Dotted keys are owned by sub-repositories (PluginRepository,
    # post_processing/config_store.py) that bypass the encrypt/decrypt layer.
    # Encrypting them would produce ciphertext those repos read verbatim.
    assert not is_sensitive_key("plugin.foo.access_token")
    assert not is_sensitive_key("plugin.x.client_secret")
    assert not is_sensitive_key("post_processing.emby.api_key")
    assert not is_sensitive_key("backend.deepl.some_token")


def test_plain_secret_suffix_is_sensitive():
    assert is_sensitive_key("webhook_secret")
    assert is_sensitive_key("session_secret")
