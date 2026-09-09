"""HTTP tests for routes/config/onboarding.py — status flags and completion.

Both cases here come from forgejo #14: an install whose onboarding was
completed through the API still got the first-run modal thrown back at it,
and its status claimed to have no providers while /api/v1/providers listed an
active one.
"""


def _get_entry(key):
    from db.config import get_config_entry

    return get_config_entry(key)


def _set_entry(key, value):
    from db.config import save_config_entry

    save_config_entry(key, value)


def test_completing_onboarding_also_satisfies_the_first_run_wizard(client):
    """Finishing onboarding must silence the first-run modal.

    The modal reads ``setup_wizard_completed`` from /system/setup/status while
    onboarding writes ``onboarding_completed`` — two independent flags. The UI
    path happens to call both endpoints; anyone provisioning through the API
    called only this one and got the setup dialog back on the next visit,
    despite a finished install (forgejo #14).
    """
    with client.application.app_context():
        _set_entry("onboarding_completed", "false")
        _set_entry("setup_wizard_completed", "false")

    resp = client.post("/api/v1/onboarding/complete")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "completed"

    with client.application.app_context():
        assert _get_entry("onboarding_completed") == "true"
        assert _get_entry("setup_wizard_completed") == "true"

    status = client.get("/api/v1/system/setup/status")
    assert status.status_code == 200
    assert status.get_json()["wizard_completed"] is True


def test_completing_twice_still_reports_already_completed(client):
    """The one-way guard stays — replaying the call must not redo side effects."""
    with client.application.app_context():
        _set_entry("onboarding_completed", "true")

    resp = client.post("/api/v1/onboarding/complete")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "already_completed"


def test_has_providers_follows_the_provider_list_not_three_api_keys(client, monkeypatch):
    """An enabled provider counts, whether or not it needs an API key.

    The flag used to test three hardcoded key fields, so an install running on
    customapi — or on any of the keyless providers — reported
    ``has_providers: false`` while /api/v1/providers listed it as enabled. Two
    endpoints, one truth, contradicting each other (forgejo #14).
    """
    import routes.config.onboarding as onboarding_routes

    monkeypatch.setattr(
        onboarding_routes,
        "_enabled_provider_names",
        lambda: ["customapi"],
    )
    resp = client.get("/api/v1/onboarding/status")
    assert resp.status_code == 200
    assert resp.get_json()["has_providers"] is True


def test_has_providers_is_false_when_nothing_is_enabled(client, monkeypatch):
    """The flag still says no when the install really has no provider."""
    import routes.config.onboarding as onboarding_routes

    monkeypatch.setattr(onboarding_routes, "_enabled_provider_names", list)
    resp = client.get("/api/v1/onboarding/status")
    assert resp.status_code == 200
    assert resp.get_json()["has_providers"] is False
