"""scheduler infrastructure

Revision ID: dc8da0c509a8
Revises: p4a_readd_wanted_sonarr_idx
Create Date: 2026-04-18

Creates both:
- scheduler_job_runs: run history owned by us
- apscheduler_jobs: mirrors SQLAlchemyJobStore's schema so it's
  Alembic-tracked and survives library version upgrades
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "dc8da0c509a8"
down_revision = "p4a_readd_wanted_sonarr_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scheduler_job_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "triggered_by",
            sa.String(16),
            nullable=False,
            server_default="schedule",
        ),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_scheduler_job_runs_job_id_started_at",
        "scheduler_job_runs",
        ["job_id", "started_at"],
    )
    op.create_index(
        "ix_scheduler_job_runs_started_at",
        "scheduler_job_runs",
        ["started_at"],
    )
    op.create_index(
        "ix_scheduler_job_runs_status",
        "scheduler_job_runs",
        ["status"],
    )

    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.Unicode(191), primary_key=True),
        sa.Column("next_run_time", sa.Float(precision=25), nullable=True),
        sa.Column("job_state", sa.LargeBinary, nullable=False),
    )
    op.create_index(
        "ix_apscheduler_jobs_next_run_time",
        "apscheduler_jobs",
        ["next_run_time"],
    )


def downgrade():
    op.drop_index(
        "ix_apscheduler_jobs_next_run_time",
        table_name="apscheduler_jobs",
    )
    op.drop_table("apscheduler_jobs")
    op.drop_index(
        "ix_scheduler_job_runs_status",
        table_name="scheduler_job_runs",
    )
    op.drop_index(
        "ix_scheduler_job_runs_started_at",
        table_name="scheduler_job_runs",
    )
    op.drop_index(
        "ix_scheduler_job_runs_job_id_started_at",
        table_name="scheduler_job_runs",
    )
    op.drop_table("scheduler_job_runs")
