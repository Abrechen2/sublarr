"""sublarr sync — synchronize subtitle timing to video."""
import os
import sys

import click

from cli.client import SublarrAPIError


@click.command()
@click.option("--subtitle", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Subtitle file to sync.")
@click.option("--video", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Reference video file.")
@click.option("--engine", default="ffsubsync", type=click.Choice(["ffsubsync", "alass"]),
              show_default=True, help="Sync engine.")
@click.pass_context
def sync(ctx: click.Context, subtitle: str, video: str, engine: str) -> None:
    """Sync SUBTITLE timing against VIDEO using ffsubsync or alass."""
    sub_path = os.path.abspath(subtitle)
    vid_path = os.path.abspath(video)
    client = ctx.obj["client"]
    click.echo(f"Syncing {os.path.basename(sub_path)} to {os.path.basename(vid_path)} via {engine}...")
    try:
        result = client.post(
            "/tools/auto-sync",
            json={"file_path": sub_path, "video_path": vid_path, "engine": engine},
        )
        msg = f"Done — status: {result.get('status', 'unknown')}"
        if result.get("shift_ms") is not None:
            msg += f", shift: {result['shift_ms']} ms"
        click.echo(msg)
    except SublarrAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
