"""Initial schema - all tables

Revision ID: 001_initial
Revises:
Create Date: 2026-03-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, ENUM as PgEnum

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create all enum types first (explicitly, before any table references them).
    # PostgreSQL has no CREATE TYPE IF NOT EXISTS, so use DO blocks instead.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE scan_status AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE phase_status AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE severity AS ENUM ('critical', 'high', 'medium', 'low', 'info');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE finding_status AS ENUM ('open', 'confirmed', 'false_positive', 'resolved');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE target_type AS ENUM ('subdomain', 'ip', 'email', 'url');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    # Scans — reference enum types by name with create_type=False so SQLAlchemy
    # does not attempt to emit a second CREATE TYPE statement
    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_uid", sa.String(100), nullable=False),
        sa.Column("target_domain", sa.String(255), nullable=False),
        sa.Column("status", PgEnum(name="scan_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("current_phase", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", JSON(), nullable=False, server_default="{}"),
        sa.Column("results_dir", sa.String(500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_uid"),
    )
    op.create_index("ix_scans_scan_uid", "scans", ["scan_uid"])
    op.create_index("ix_scans_target_domain", "scans", ["target_domain"])

    # Scan phases
    op.create_table(
        "scan_phases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_number", sa.Integer(), nullable=False),
        sa.Column("phase_name", sa.String(50), nullable=False),
        sa.Column("status", PgEnum(name="phase_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("tool_statuses", JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Targets
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", PgEnum(name="target_type", create_type=False), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("source_tool", sa.String(100), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_ips", JSON(), nullable=True),
        sa.Column("open_ports", JSON(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("http_title", sa.String(500), nullable=True),
        sa.Column("technologies", JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_targets_scan_id", "targets", ["scan_id"])
    op.create_index("ix_targets_value", "targets", ["value"])

    # Findings
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("targets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("severity", PgEnum(name="severity", create_type=False), nullable=False),
        sa.Column("source_tool", sa.String(100), nullable=False),
        sa.Column("template_id", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("reference_urls", JSON(), nullable=False, server_default="[]"),
        sa.Column("affected_url", sa.String(1000), nullable=True),
        sa.Column("affected_host", sa.String(255), nullable=True),
        sa.Column("affected_port", sa.Integer(), nullable=True),
        sa.Column("status", PgEnum(name="finding_status", create_type=False), nullable=False, server_default="open"),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("defectdojo_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_scan_id", "findings", ["scan_id"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_source_tool", "findings", ["source_tool"])


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("targets")
    op.drop_table("scan_phases")
    op.drop_table("scans")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS finding_status")
    op.execute("DROP TYPE IF EXISTS severity")
    op.execute("DROP TYPE IF EXISTS target_type")
    op.execute("DROP TYPE IF EXISTS phase_status")
    op.execute("DROP TYPE IF EXISTS scan_status")
