"""What counts as a writable config key — the one place that got it wrong.

Both call sites derived the set from ``Settings.model_fields``. ``Settings`` is
a plain composite class and has no ``model_fields``, so the ``hasattr`` guard
fell through to ``set()`` every single time. The two endpoints then failed in
opposite directions from that same empty set:

* ``POST /config/import`` is fail-closed — an empty set means "cannot determine
  valid keys", so it answered **500 to every import that has ever been made**.
  No test covered the endpoint, which is why a fully dead route went unnoticed.
* ``POST /config`` reads ``if not valid_keys or key in valid_keys``, so the
  empty set disabled key validation entirely and every key was accepted.

The real set cannot be the model fields alone: 15 of the 73 config keys on the
reference install are not settings fields (``ui_password_hash``,
``translation_quality_threshold``, ``usage_stats_consent``, the
``cleanup_*_seeded`` markers …). Validating against the models alone would stop
the UI from saving them, so a key already present in ``config_entries`` counts
as valid too, alongside the dotted extension keys that were always allowed.
"""

from __future__ import annotations


def test_import_does_not_reject_every_payload(client):
    """The regression: this endpoint answered 500 no matter what was sent."""
    resp = client.post("/api/v1/config/import", json={"log_level": "INFO"})
    assert resp.status_code != 500, f"/config/import still fails closed: {resp.get_json()}"
    assert resp.status_code == 200, resp.get_json()


def test_valid_keys_covers_model_fields_and_stored_keys():
    from routes.config.keys import writable_config_keys

    keys = writable_config_keys()
    assert "log_level" in keys, "a plain settings field must be writable"
    assert keys, "the set must never be empty — that is the bug this replaces"


def test_dotted_extension_keys_stay_allowed():
    from routes.config.keys import is_writable_config_key

    assert is_writable_config_key("backend.ollama.url")
    assert is_writable_config_key("whisper.subgen.url")


def test_unknown_flat_key_is_not_writable():
    from routes.config.keys import is_writable_config_key

    assert not is_writable_config_key("definitely_not_a_setting_xyz")


def test_settings_the_ui_writes_are_declared_fields(client):
    """Every key the settings UI writes must be a real field.

    Six were not: base_url and the translation_memory_*/translation_quality_*
    pairs. That had a second, visible consequence — GET /config returns
    ``get_safe_config()``, which is model fields only, so the UI never saw the
    stored value and rendered its own fallback instead. The reference install
    has translation_quality_threshold = 35 while the page showed 50.
    """
    from routes.config.keys import writable_config_keys

    ui_written = {
        "base_url",
        "translation_memory_enabled",
        "translation_memory_similarity_threshold",
        "translation_quality_enabled",
        "translation_quality_threshold",
        "translation_quality_max_retries",
    }
    missing = ui_written - writable_config_keys()
    assert not missing, f"the settings UI writes keys the config layer rejects: {sorted(missing)}"

    body = client.get("/api/v1/config").get_json()
    invisible = {k for k in ui_written if k not in body}
    assert not invisible, f"GET /config hides settings the UI must render: {sorted(invisible)}"


def test_unknown_key_is_rejected_instead_of_silently_stored(client):
    """The point of the whole exercise: a typo must not answer 200.

    ``valid_keys`` was always empty, so ``if not valid_keys or ...`` accepted
    every key name and wrote it. A misspelled setting reported success and then
    did nothing, with no way to notice.
    """
    from db.config import get_config_entry

    resp = client.put("/api/v1/config", json={"log_levl": "DEBUG"})

    assert resp.status_code == 400, resp.get_json()
    assert get_config_entry("log_levl") is None, "the bogus key was stored anyway"


def test_a_real_setting_still_saves(client):
    """The guard must not turn into a wall."""
    resp = client.put("/api/v1/config", json={"translation_quality_threshold": 35})
    assert resp.status_code == 200, resp.get_json()


def test_dotted_extension_keys_are_still_accepted(client):
    resp = client.put("/api/v1/config", json={"translation.context_window_size": "4096"})
    assert resp.status_code == 200, resp.get_json()


def test_auth_secrets_cannot_be_written_through_config(client):
    """A side effect worth keeping: ui_password_hash is not a settings field,
    so with key validation live this endpoint stops being a way to set it."""
    from db.config import get_config_entry

    resp = client.put("/api/v1/config", json={"ui_password_hash": "$2b$12$forged"})

    assert resp.status_code == 400, resp.get_json()
    assert get_config_entry("ui_password_hash") is None
