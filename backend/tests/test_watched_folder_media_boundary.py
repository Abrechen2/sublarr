"""Watched folders must sit inside the media folder.

A folder outside ``media_path`` used to be accepted with only a log line. Its
files were then scanned, but search, download, sync and the track tools
refused them (403), so the library showed entries nothing worked on. Adding
such a folder is now refused with a message that says how to mount it, and
the folder list flags any existing folder outside the media folder.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from routes.standalone.folders import _validate_watched_folder_path


@pytest.fixture
def media_root(tmp_path):
    root = tmp_path / "media"
    (root / "anime").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    return root


def _with_media(path):
    return patch("config.get_settings", return_value=SimpleNamespace(media_path=str(path)))


def test_a_folder_inside_the_media_folder_is_accepted(media_root):
    with _with_media(media_root):
        assert _validate_watched_folder_path(str(media_root / "anime")) is None


def test_the_media_folder_itself_is_accepted(media_root):
    with _with_media(media_root):
        assert _validate_watched_folder_path(str(media_root)) is None


def test_a_folder_outside_the_media_folder_is_refused(media_root):
    with _with_media(media_root):
        err = _validate_watched_folder_path(str(media_root.parent / "elsewhere"))
    assert err is not None
    assert "outside the media folder" in err
    assert str(media_root) in err


def test_a_symlink_into_another_tree_is_refused(media_root):
    link = media_root / "link"
    link.symlink_to(media_root.parent / "elsewhere", target_is_directory=True)
    with _with_media(media_root):
        assert _validate_watched_folder_path(str(link)) is not None


def test_without_a_media_folder_there_is_no_boundary(media_root):
    with _with_media(""):
        assert _validate_watched_folder_path(str(media_root.parent / "elsewhere")) is None


def test_the_api_refuses_an_outside_folder(client, media_root):
    with _with_media(media_root):
        resp = client.post(
            "/api/v1/standalone/folders", json={"path": str(media_root.parent / "elsewhere")}
        )
    assert resp.status_code == 400
    assert "outside the media folder" in resp.get_json()["error"]


def test_the_folder_list_flags_folders_outside_the_media_folder(client, media_root):
    folders = [
        {
            "id": 1,
            "path": str(media_root / "anime"),
            "label": "",
            "media_type": "auto",
            "enabled": True,
        },
        {
            "id": 2,
            "path": str(media_root.parent / "elsewhere"),
            "label": "",
            "media_type": "auto",
            "enabled": True,
        },
    ]
    with _with_media(media_root), patch("db.standalone.get_watched_folders", return_value=folders):
        data = client.get("/api/v1/standalone/folders").get_json()
    assert [f["outside_media_path"] for f in data] == [False, True]
