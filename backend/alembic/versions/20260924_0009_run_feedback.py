"""Add run_feedback table (Phase 3H).

Revision ID: 20260924_0009
Revises: 20260924_0008
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0009"
down_revision = "20260924_0008"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("run_feedback"):
        op.create_table(
            "run_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("rating", sa.String(length=10), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_run_feedback_agent_run_id", "run_feedback", ["agent_run_id"])


def downgrade() -> None:
    if _has_table("run_feedback"):
        op.drop_index("ix_run_feedback_agent_run_id", table_name="run_feedback")
        op.drop_table("run_feedback")
