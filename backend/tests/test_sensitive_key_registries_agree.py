"""What the API masks is also what the database encrypts.

Two registries decide about secrets: ``config_settings.is_sensitive_config_key``
(masking in GET / export) and ``sensitive_keys.is_sensitive_key`` (encryption at
rest, import exclusion). The new ``opensubtitlescom_subliminal_apikey`` (#61 A01)
was masked but would have been stored in plain text, and ``tvdb_pin`` already
was — a security review of the branch caught the drift.
"""

from config_settings import BootSettings, UISettings, is_sensitive_config_key
from sensitive_keys import is_sensitive_key

#: Masked although not a secret: the NAME of the header the API key goes in.
NOT_A_SECRET = {"customapi_api_key_header"}
#: Boot settings from the environment, never stored in config_entries.
ENV_ONLY = {"database_url", "redis_url"}


def test_every_masked_setting_is_encrypted_at_rest():
    fields = set(UISettings.model_fields) | set(BootSettings.model_fields)
    masked = {k for k in fields if is_sensitive_config_key(k)} - NOT_A_SECRET - ENV_ONLY

    assert {k for k in masked if not is_sensitive_key(k)} == set()


def test_every_encrypted_setting_is_masked():
    fields = set(UISettings.model_fields)

    assert {k for k in fields if is_sensitive_key(k) and not is_sensitive_config_key(k)} == set()


def test_the_new_provider_key_and_the_tvdb_pin_are_secrets():
    assert is_sensitive_key("opensubtitlescom_subliminal_apikey")
    assert is_sensitive_key("tvdb_pin")
