from unittest.mock import MagicMock
from click.testing import CliRunner
from cli.commands.search import search


class TestSearchCommand:
    def test_search_triggers_batch(self):
        client = MagicMock()
        client.get.return_value = {"items": [{"id": 1}, {"id": 2}], "total": 2}
        client.post.return_value = {"status": "started"}
        result = CliRunner().invoke(search, ["--series-id", "42"], obj={"client": client})
        assert result.exit_code == 0
        client.get.assert_called_once_with("/wanted", params={"series_id": 42, "per_page": 200})
        client.post.assert_called_once_with("/wanted/batch-search", json={"item_ids": [1, 2]})
        assert "2" in result.output

    def test_search_no_items(self):
        client = MagicMock()
        client.get.return_value = {"items": [], "total": 0}
        result = CliRunner().invoke(search, ["--series-id", "99"], obj={"client": client})
        assert result.exit_code == 0
        client.post.assert_not_called()
        assert "No wanted" in result.output

    def test_search_requires_series_id(self):
        result = CliRunner().invoke(search, [], obj={"client": MagicMock()})
        assert result.exit_code != 0

    def test_search_api_error(self):
        from cli.client import SublarrAPIError
        client = MagicMock()
        client.get.side_effect = SublarrAPIError("Cannot connect")
        result = CliRunner().invoke(search, ["--series-id", "1"], obj={"client": client})
        assert result.exit_code == 1
        assert "Error" in result.output
