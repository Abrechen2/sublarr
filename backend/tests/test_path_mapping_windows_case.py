"""Windows paths ignore case; the path mapping must, too."""

from types import SimpleNamespace
from unittest.mock import patch

from config_utils import map_path


def _map(path, mapping):
    with patch("config.get_settings", return_value=SimpleNamespace(path_mapping=mapping)):
        return map_path(path)


def test_a_differently_cased_drive_and_folder_still_maps():
    assert _map(r"d:\tv\Show\e1.mkv", r"D:\TV=/media/tv") == "/media/tv/Show/e1.mkv"


def test_the_rest_of_the_path_keeps_its_case():
    assert _map(r"D:\TV\Show\E1.mkv", r"d:\tv=/media/tv") == "/media/tv/Show/E1.mkv"


def test_posix_paths_stay_case_sensitive():
    assert _map("/Data/TV/e1.mkv", "/data/tv=/media/tv") == "/Data/TV/e1.mkv"
