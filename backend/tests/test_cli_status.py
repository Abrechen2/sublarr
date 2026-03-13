from unittest.mock import MagicMock
from click.testing import CliRunner
from cli.commands.status import status


class TestStatusCommand:
    def _make_client(self):
        client = MagicMock()
        client.get.side_effect = lambda path, **kw: (
            {"jobs": [
                {"id": "abc123ff", "status": "running", "file_path": "/media/ep1.ass", "created_at": "2026-03-13T10:00:00"},
            ], "total": 1}
            if "jobs" in path
            else {"tasks": [
                {"name": "wanted_scanner", "display_name": "Wanted Scanner", "running": False, "last_run": "2026-03-13T08:00:00"},
            ]}
        )
        return client

    def test_shows_jobs_and_tasks(self):
        result = CliRunner().invoke(status, [], obj={"client": self._make_client()})
        assert result.exit_code == 0
        assert "running" in result.output
        assert "abc123ff" in result.output
        assert "Wanted Scanner" in result.output

    def test_running_flag_passes_status_param(self):
        client = MagicMock()
        client.get.side_effect = lambda path, **kw: (
            {"jobs": [], "total": 0} if "jobs" in path else {"tasks": []}
        )
        CliRunner().invoke(status, ["--running"], obj={"client": client})
        params = client.get.call_args_list[0].kwargs.get("params", {})
        assert params.get("status") == "running"

    def test_api_error_exits_nonzero(self):
        from cli.client import SublarrAPIError
        client = MagicMock()
        client.get.side_effect = SublarrAPIError("Cannot connect")
        result = CliRunner().invoke(status, [], obj={"client": client})
        assert result.exit_code == 1
        assert "Error" in result.output
