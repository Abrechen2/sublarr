"""sublarr translate — translate a subtitle file via the Sublarr API."""

import os
import sys

import click

from cli.client import SublarrAPIError


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--force", is_flag=True, default=False, help="Re-translate even if target exists.")
@click.pass_context
def translate(ctx: click.Context, file: str, force: bool) -> None:
    """Translate FILE (.ass or .srt). FILE must be under the configured media_path."""
    file_path = os.path.abspath(file)
    client = ctx.obj["client"]
    try:
        result = client.post("/translate/sync", json={"file_path": file_path, "force": force})
        if "job_id" in result:
            click.echo(
                f"Queued as job {result['job_id']} (status: {result.get('status', 'queued')})"
            )
            click.echo("Poll with: sublarr status")
        else:
            click.echo(f"Done: {result.get('output_path', '?')}")
    except SublarrAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
