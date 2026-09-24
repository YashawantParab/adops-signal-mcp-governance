"""Add requested_provider/fallback_reason/execution_status to gate_decisions
(Jev-readiness observability - see docs/jev-integration-notes.md).

Revision ID: 20260925_0010
Revises: 20260924_0009
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260925_0010"
down_revision = "20260924_0009"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("gate_decisions", "requested_provider"):
        op.add_column("gate_decisions", sa.Column("requested_provider", sa.String(length=20), nullable=True))
    if not _has_column("gate_decisions", "fallback_reason"):
        op.add_column("gate_decisions", sa.Column("fallback_reason", sa.Text(), nullable=True))
    if not _has_column("gate_decisions", "execution_status"):
        op.add_column(
            "gate_decisions",
            sa.Column("execution_status", sa.String(length=80), nullable=False, server_default="executed"),
        )


def downgrade() -> None:
    if _has_column("gate_decisions", "execution_status"):
        op.drop_column("gate_decisions", "execution_status")
    if _has_column("gate_decisions", "fallback_reason"):
        op.drop_column("gate_decisions", "fallback_reason")
    if _has_column("gate_decisions", "requested_provider"):
        op.drop_column("gate_decisions", "requested_provider")
