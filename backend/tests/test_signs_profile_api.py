"""Profile switches for signs & songs travel through the API, the filters and backups."""


def _create(client, **extra):
    payload = {
        "name": "Dub",
        "source_language": "ja",
        "source_language_name": "Japanese",
        "target_languages": ["en"],
        "target_language_names": ["English"],
        **extra,
    }
    resp = client.post("/api/v1/language-profiles", json=payload)
    assert resp.status_code in (200, 201), resp.get_json()
    return resp.get_json().get("id") or resp.get_json()["profile"]["id"]


def _get(client, profile_id):
    profiles = client.get("/api/v1/language-profiles").get_json()["profiles"]
    return next(p for p in profiles if p["id"] == profile_id)


def test_new_profiles_download_full_and_do_not_prefer_signs(client):
    profile = _get(client, _create(client))

    assert (profile["prefer_signs"], profile["download_full"]) == (False, True)


def test_the_switches_are_saved_and_updated(client):
    profile_id = _create(client, prefer_signs=True, download_full=False)
    assert (
        _get(client, profile_id)["prefer_signs"],
        _get(client, profile_id)["download_full"],
    ) == (
        True,
        False,
    )

    resp = client.put(f"/api/v1/language-profiles/{profile_id}", json={"download_full": True})
    assert resp.status_code == 200, resp.get_json()
    assert _get(client, profile_id)["download_full"] is True


def test_profile_filters_carry_the_switches(client):
    from db.models.core import LanguageProfile
    from wanted_search.profile_filters import load_profile_filters

    pf = load_profile_filters(LanguageProfile(prefer_signs=1, download_full=0))

    assert (pf["prefer_signs"], pf["download_full"]) == (True, False)
    assert load_profile_filters(None)["download_full"] is True


def test_a_backup_brings_profiles_back_with_their_languages(client):
    """The export writes source_language/target_languages; the import read
    source_lang/target_langs, so restored profiles had no target languages."""
    import io
    import json
    import zipfile

    _create(client, prefer_signs=True, download_full=False)
    exported = [p for p in client.get("/api/v1/language-profiles").get_json()["profiles"]]
    for p in exported:
        p["name"] = p["name"] + " restored"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("profiles.json", json.dumps(exported))
    buf.seek(0)

    restored_names = {p["name"] for p in exported}
    resp = client.post(
        "/api/v1/api-keys/import",
        data={"file": (buf, "backup.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["profiles_imported"] == len(exported), resp.get_json()

    restored = [
        p
        for p in client.get("/api/v1/language-profiles").get_json()["profiles"]
        if p["name"] in restored_names
    ]
    assert {p["name"] for p in restored} == restored_names
    dub = next(p for p in restored if p["name"] == "Dub restored")
    assert dub["target_languages"] == ["en"]
    assert (dub["prefer_signs"], dub["download_full"]) == (True, False)
