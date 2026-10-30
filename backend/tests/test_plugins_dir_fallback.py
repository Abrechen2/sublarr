"""An uncreatable plugins_dir falls back to one private temp folder per process."""

import os
import stat
from unittest.mock import patch

import app as app_module
from app import usable_plugins_dir


def test_a_creatable_plugins_dir_is_used(tmp_path):
    target = tmp_path / "plugins"

    assert usable_plugins_dir(str(target)) == str(target)
    assert target.is_dir()


def test_every_start_in_a_process_shares_one_private_fallback(tmp_path, monkeypatch):
    real_makedirs = os.makedirs
    monkeypatch.setattr(app_module, "_fallback_plugins_dir", None)

    def makedirs(path, *args, **kwargs):
        if path == "/config/plugins":
            raise PermissionError(path)
        return real_makedirs(path, *args, **kwargs)

    with (
        patch("app.os.makedirs", side_effect=makedirs),
        patch("tempfile.tempdir", str(tmp_path)),
    ):
        first = usable_plugins_dir("/config/plugins")
        second = usable_plugins_dir("/config/plugins")

    assert first == second
    assert os.path.dirname(first) == str(tmp_path)
    assert len(os.listdir(tmp_path)) == 1
    # Plugins are code: the folder must not be writable by anyone else.
    assert stat.S_IMODE(os.stat(first).st_mode) == 0o700
