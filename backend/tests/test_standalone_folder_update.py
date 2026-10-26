"""PUT /standalone/folders/<id> edits the folder in place.

Found by the 1.18 end-to-end test: a PUT with a new path went through the
path-keyed upsert, so it created a second folder and returned the old one
unchanged. Moving a folder now updates the same row, refuses another
folder's path, and removes the titles the new path no longer covers.
"""

from __future__ import annotations

from tests.test_standalone_folder_removal import _folder, _ids, _series, api, media  # noqa: F401, F811 — fixtures


def test_put_with_a_new_path_updates_the_folder_in_place(api, media):  # noqa: F811
    fid = _folder(media / "A")
    s_old = _series(media / "A" / "Show")

    resp = api.put(f"/api/v1/standalone/folders/{fid}", json={"path": str(media / "New")})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == fid
    assert body["path"] == str(media / "New")
    assert _ids("watched_folders") == {fid}
    assert s_old not in _ids("standalone_series")


def test_put_keeps_titles_still_under_the_new_path(api, media):  # noqa: F811
    fid = _folder(media / "A")
    sid = _series(media / "A" / "Show")

    resp = api.put(f"/api/v1/standalone/folders/{fid}", json={"path": str(media)})

    assert resp.status_code == 200
    assert resp.get_json()["id"] == fid
    assert _ids("standalone_series") == {sid}


def test_put_to_the_path_of_another_folder_is_a_conflict(api, media):  # noqa: F811
    fid = _folder(media / "A")
    other = _folder(media / "AB")

    resp = api.put(f"/api/v1/standalone/folders/{fid}", json={"path": str(media / "AB")})

    assert resp.status_code == 409
    assert _ids("watched_folders") == {fid, other}


def test_put_label_only_keeps_titles(api, media):  # noqa: F811
    fid = _folder(media / "A")
    sid = _series(media / "A" / "Show")

    resp = api.put(
        f"/api/v1/standalone/folders/{fid}",
        json={"path": str(media / "A"), "label": "Anime", "enabled": False},
    )

    assert resp.status_code == 200
    assert resp.get_json()["label"] == "Anime"
    assert _ids("standalone_series") == {sid}


def test_put_to_a_forbidden_path_is_refused(api, media):  # noqa: F811
    fid = _folder(media / "A")

    resp = api.put(f"/api/v1/standalone/folders/{fid}", json={"path": "/etc"})

    assert resp.status_code == 400
