"""Store classified investigation intent.

Revision ID: 20260703_0003
Revises: 20260703_0002
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_0003"
down_revision = "20260703_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("agent_audit_logs")}
    if "query_intent" not in columns:
        op.add_column(
            "agent_audit_logs",
            sa.Column("query_intent", sa.String(length=60), nullable=False, server_default="comprehensive"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("agent_audit_logs")}
    if "query_intent" in columns:
        op.drop_column("agent_audit_logs", "query_intent")
