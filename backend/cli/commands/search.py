"""sublarr search — find and download missing subtitles for a series."""
import sys

import click

from cli.client import SublarrAPIError


@click.command()
@click.option("--series-id", required=True, type=int, help="Sonarr series ID to search.")
@click.pass_context
def search(ctx: click.Context, series_id: int) -> None:
    """Search subtitle providers for missing subs in a series."""
    client = ctx.obj["client"]
    try:
        data = client.get("/wanted", params={"series_id": series_id, "per_page": 200})
        items = data.get("items", [])
        if not items:
            click.echo(f"No wanted items found for series {series_id}.")
            return
        item_ids = [item["id"] for item in items]
        click.echo(f"Searching {len(item_ids)} wanted item(s) for series {series_id}...")
        result = client.post("/wanted/batch-search", json={"item_ids": item_ids})
        click.echo(f"Search started — status: {result.get('status', 'unknown')}")
    except SublarrAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
