from unittest.mock import MagicMock
from click.testing import CliRunner
from cli.commands.translate import translate


class TestTranslateCommand:
    def test_sync_response(self, tmp_path):
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        client = MagicMock()
        client.post.return_value = {"success": True, "output_path": str(tmp_path / "ep.de.ass")}
        result = CliRunner().invoke(translate, [str(sub)], obj={"client": client})
        assert result.exit_code == 0
        client.post.assert_called_once_with(
            "/translate/sync", json={"file_path": str(sub), "force": False}
        )
        assert "ep.de.ass" in result.output

    def test_queued_response(self, tmp_path):
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        client = MagicMock()
        client.post.return_value = {"job_id": "abc123", "status": "queued"}
        result = CliRunner().invoke(translate, [str(sub)], obj={"client": client})
        assert result.exit_code == 0
        assert "abc123" in result.output

    def test_force_flag(self, tmp_path):
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        client = MagicMock()
        client.post.return_value = {"success": True, "output_path": "/out.ass"}
        CliRunner().invoke(translate, [str(sub), "--force"], obj={"client": client})
        assert client.post.call_args.kwargs["json"]["force"] is True

    def test_file_not_found(self):
        result = CliRunner().invoke(translate, ["/nope.ass"], obj={"client": MagicMock()})
        assert result.exit_code != 0

    def test_api_error(self, tmp_path):
        from cli.client import SublarrAPIError
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        client = MagicMock()
        client.post.side_effect = SublarrAPIError("Not under media_path")
        result = CliRunner().invoke(translate, [str(sub)], obj={"client": client})
        assert result.exit_code == 1
        assert "Error" in result.output
