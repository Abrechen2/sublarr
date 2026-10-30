"""An uncreatable plugins_dir falls back to one fixed temp folder, not a new one per start."""

import os
from unittest.mock import patch

from app import usable_plugins_dir


def test_a_creatable_plugins_dir_is_used(tmp_path):
    target = tmp_path / "plugins"

    assert usable_plugins_dir(str(target)) == str(target)
    assert target.is_dir()


def test_every_start_shares_one_fallback_folder(tmp_path):
    real_makedirs = os.makedirs

    def makedirs(path, *args, **kwargs):
        if path == "/config/plugins":
            raise PermissionError(path)
        return real_makedirs(path, *args, **kwargs)

    with (
        patch("app.os.makedirs", side_effect=makedirs),
        patch("tempfile.gettempdir", return_value=str(tmp_path)),
    ):
        first = usable_plugins_dir("/config/plugins")
        second = usable_plugins_dir("/config/plugins")

    assert first == second == str(tmp_path / "sublarr_plugins")
    assert os.listdir(tmp_path) == ["sublarr_plugins"]
