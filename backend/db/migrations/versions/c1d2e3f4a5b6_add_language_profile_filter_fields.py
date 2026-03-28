"""Add mustContain, mustNotContain, cutoff_language, audio_exclude columns to language_profiles."""

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN must_contain_json TEXT NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN must_not_contain_json TEXT NOT NULL DEFAULT '[]'"
    )
    op.execute("ALTER TABLE language_profiles ADD COLUMN cutoff_language TEXT NOT NULL DEFAULT ''")
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN "
        "audio_exclude_languages_json TEXT NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN — recreate table without these columns
    op.execute(
        "CREATE TABLE language_profiles_backup AS "
        "SELECT id, name, source_language, source_language_name, "
        "target_languages_json, target_language_names_json, is_default, "
        "translation_backend, fallback_chain_json, forced_preference, "
        "created_at, updated_at FROM language_profiles"
    )
    op.execute("DROP TABLE language_profiles")
    op.execute("ALTER TABLE language_profiles_backup RENAME TO language_profiles")
