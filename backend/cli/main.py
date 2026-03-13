"""Sublarr CLI — root group and global options."""
import click

from cli.client import SublarrClient


@click.group()
@click.option(
    "--url",
    envvar="SUBLARR_URL",
    default="http://localhost:5765",
    show_default=True,
    help="Sublarr API base URL.",
)
@click.option(
    "--api-key",
    envvar="SUBLARR_API_KEY",
    default="",
    help="API key (or set SUBLARR_API_KEY env var).",
)
@click.pass_context
def cli(ctx: click.Context, url: str, api_key: str) -> None:
    """Sublarr subtitle manager — command-line interface."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = SublarrClient(url, api_key)
