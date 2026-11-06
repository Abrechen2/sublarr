"""is_safe_path refuses a relative path under an absolute base.

A relative path is resolved against the process's working directory, not
against base_dir, so whether it counts as inside depended on where the
process was started. test_stream_windows_traversal_blocked failed whenever
the checkout sat below the temp folder (the media base in tests), because
"C:/Windows/..." is a relative path on Linux. Every caller hands over an
absolute library path.
"""

import os

from security_utils import is_safe_path


def test_a_relative_path_is_refused_even_when_cwd_is_inside_the_base(tmp_path, monkeypatch):
    (tmp_path / "C:").mkdir()
    monkeypatch.chdir(tmp_path)
    assert not is_safe_path("C:/Windows/System32/drivers/etc/hosts", str(tmp_path))
    assert not is_safe_path("movie.mkv", str(tmp_path))


def test_an_absolute_path_inside_the_base_is_still_safe(tmp_path):
    assert is_safe_path(os.path.join(str(tmp_path), "movie.mkv"), str(tmp_path))
