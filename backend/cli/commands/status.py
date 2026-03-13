"""sublarr status — show running jobs and background task state."""
import sys

import click

from cli.client import SublarrAPIError


@click.command()
@click.option("--running", "only_running", is_flag=True, help="Show only in-progress jobs.")
@click.pass_context
def status(ctx: click.Context, only_running: bool) -> None:
    """Show active translation jobs and scheduler task status."""
    client = ctx.obj["client"]
    try:
        params = {"per_page": 20}
        if only_running:
            params["status"] = "running"
        jobs_data = client.get("/jobs", params=params)
        tasks_data = client.get("/tasks")
    except SublarrAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    jobs = jobs_data.get("jobs", [])
    total = jobs_data.get("total", 0)
    click.echo(f"\n=== Translation Jobs (showing {len(jobs)} of {total}) ===")
    if not jobs:
        click.echo("  (none)")
    for job in jobs:
        jid = str(job.get("id") or "?")[:8]
        st = job.get("status", "?")
        fp = job.get("file_path", "?")
        click.echo(f"  [{jid}] {st:10s}  {fp}")

    tasks = tasks_data.get("tasks", [])
    click.echo("\n=== Background Tasks ===")
    if not tasks:
        click.echo("  (none)")
    for task in tasks:
        name = task.get("display_name") or task.get("name", "?")
        running = "RUNNING" if task.get("running") else "idle"
        last = task.get("last_run") or "never"
        click.echo(f"  {name:30s}  {running:8s}  last: {last}")
    click.echo("")
