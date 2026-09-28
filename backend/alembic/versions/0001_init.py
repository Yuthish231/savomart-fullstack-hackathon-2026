"""init: extensions, schemas, users, jobs, data sources

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")  # fuzzy duplicate-property matching
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS ref")

    ts = lambda name: sa.Column(  # noqa: E731
        name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    op.create_table(
        "user",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        ts("created_at"),
        ts("updated_at"),
        sa.CheckConstraint("role IN ('BDM','BDE','SM','SE')", name="ck_user_role_valid"),
        sa.UniqueConstraint("username", name="uq_user_username"),
        schema="app",
    )
    op.create_index("ix_app_user_role", "user", ["role"], schema="app")

    op.create_table(
        "job",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("payload", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("steps", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("result", pg.JSONB),
        sa.Column("error", sa.Text),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        ts("run_after"),
        sa.Column("locked_by", sa.String(64)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.user.id", ondelete="SET NULL", name="fk_job_created_by_user"),
        ),
        ts("created_at"),
        ts("updated_at"),
        schema="app",
    )
    op.create_index(
        "ix_job_queued",
        "job",
        ["run_after"],
        schema="app",
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.create_table(
        "data_source",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("license", sa.String(120)),
        sa.Column("as_of", sa.Date),
        ts("fetched_at"),
        sa.Column("is_mock", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("row_count", sa.Integer),
        sa.Column("notes", sa.Text),
        sa.UniqueConstraint("key", name="uq_data_source_key"),
        schema="ref",
    )


def downgrade() -> None:
    op.drop_table("data_source", schema="ref")
    op.drop_index("ix_job_queued", table_name="job", schema="app")
    op.drop_table("job", schema="app")
    op.drop_index("ix_app_user_role", table_name="user", schema="app")
    op.drop_table("user", schema="app")
