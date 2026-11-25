"""initial schema, app role and append-only audit grants

Revision ID: 0001
Revises:
"""
import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None

APP_ROLE = "dlp_app"
TABLES_RW = ["users", "transfers", "files", "findings", "approvals"]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
    )
    op.create_table(
        "transfers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sender_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("recipients", sa.Text, nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_downloads", sa.Integer, nullable=False, server_default="1"),
        sa.Column("download_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploading"),
        sa.Column("release_variant", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("transfer_id", sa.Integer, sa.ForeignKey("transfers.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("redacted_key", sa.String(512)),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String(127), nullable=False),
        sa.Column("scan_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("scan_id", sa.String(64), unique=True),
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("files.id"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("samples", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("file_id", "type"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("transfer_id", sa.Integer, sa.ForeignKey("transfers.id"), nullable=False),
        sa.Column("approver_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("transfer_id", sa.Integer),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("ua", sa.String(255), nullable=False, server_default=""),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_transfer_id", "audit_events", ["transfer_id"])

    pw = os.environ.get("APP_DB_PASSWORD", "dlp_app").replace("'", "''")
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{pw}';
          ELSE
            ALTER ROLE {APP_ROLE} LOGIN PASSWORD '{pw}';
          END IF;
        END $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for t in TABLES_RW:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE}")
    # Append-only: the runtime role may only read and insert audit rows.
    op.execute(f"GRANT SELECT, INSERT ON audit_events TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    for t in ["audit_events", "approvals", "findings", "files", "transfers", "users"]:
        op.drop_table(t)
