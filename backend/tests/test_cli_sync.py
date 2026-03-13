from unittest.mock import MagicMock
from click.testing import CliRunner
from cli.commands.sync import sync


class TestSyncCommand:
    def test_sync_success(self, tmp_path):
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        vid = tmp_path / "ep.mkv"
        vid.write_bytes(b"\x1a\x45\xdf\xa3")
        client = MagicMock()
        client.post.return_value = {"status": "done", "shift_ms": 420}
        result = CliRunner().invoke(
            sync, ["--subtitle", str(sub), "--video", str(vid)], obj={"client": client}
        )
        assert result.exit_code == 0
        client.post.assert_called_once_with(
            "/tools/auto-sync",
            json={"file_path": str(sub), "video_path": str(vid), "engine": "ffsubsync"},
        )
        assert "done" in result.output

    def test_alass_engine(self, tmp_path):
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        vid = tmp_path / "ep.mkv"
        vid.write_bytes(b"\x00")
        client = MagicMock()
        client.post.return_value = {"status": "done"}
        CliRunner().invoke(
            sync, ["--subtitle", str(sub), "--video", str(vid), "--engine", "alass"],
            obj={"client": client},
        )
        assert client.post.call_args.kwargs["json"]["engine"] == "alass"

    def test_missing_subtitle_exits(self, tmp_path):
        vid = tmp_path / "ep.mkv"
        vid.write_bytes(b"\x00")
        result = CliRunner().invoke(
            sync, ["--subtitle", "/nope.ass", "--video", str(vid)],
            obj={"client": MagicMock()},
        )
        assert result.exit_code != 0

    def test_api_error(self, tmp_path):
        from cli.client import SublarrAPIError
        sub = tmp_path / "ep.ass"
        sub.write_text("[Script Info]\n")
        vid = tmp_path / "ep.mkv"
        vid.write_bytes(b"\x00")
        client = MagicMock()
        client.post.side_effect = SublarrAPIError("Engine not installed")
        result = CliRunner().invoke(
            sync, ["--subtitle", str(sub), "--video", str(vid)], obj={"client": client}
        )
        assert result.exit_code == 1
        assert "Error" in result.output
