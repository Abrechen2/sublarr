from click.testing import CliRunner
from cli.main import cli


class TestCliMain:
    def setup_method(self):
        self.runner = CliRunner()

    def test_help_exits_zero(self):
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Sublarr" in result.output

    def test_custom_url_stored_in_context(self):
        """Passing --url should be accepted without error (needs a subcommand to do work)."""
        result = self.runner.invoke(cli, ["--url", "http://myserver:9000", "--help"])
        assert result.exit_code == 0

    def test_default_url_is_localhost(self):
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "localhost:5765" in result.output
