"""Add governed MCP agent observability fields.

Revision ID: 20260924_0005
Revises: 20260710_0004
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0005"
down_revision = "20260710_0004"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    # execution_mode backfills to "deterministic_fallback" for every existing
    # row: every agent_runs row written before this migration ran through the
    # (100% deterministic) orchestration this phase now calls the fallback
    # path, so that label is accurate history, not a guess.
    if not _has_column("agent_runs", "execution_mode"):
        op.add_column(
            "agent_runs",
            sa.Column("execution_mode", sa.String(length=40), nullable=False, server_default="deterministic_fallback"),
        )
    if not _has_column("agent_runs", "llm_provider"):
        op.add_column("agent_runs", sa.Column("llm_provider", sa.String(length=40), nullable=True))
    if not _has_column("agent_runs", "model_name"):
        op.add_column("agent_runs", sa.Column("model_name", sa.String(length=120), nullable=True))
    if not _has_column("agent_runs", "input_tokens"):
        op.add_column("agent_runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    if not _has_column("agent_runs", "output_tokens"):
        op.add_column("agent_runs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    if not _has_column("agent_runs", "total_tokens"):
        op.add_column("agent_runs", sa.Column("total_tokens", sa.Integer(), nullable=True))
    if not _has_column("agent_runs", "estimated_cost_usd"):
        op.add_column("agent_runs", sa.Column("estimated_cost_usd", sa.Float(), nullable=True))
    if not _has_column("agent_runs", "steps_used"):
        op.add_column("agent_runs", sa.Column("steps_used", sa.Integer(), nullable=True))
    if not _has_column("agent_runs", "max_steps"):
        op.add_column("agent_runs", sa.Column("max_steps", sa.Integer(), nullable=True))
    if not _has_column("agent_runs", "fallback_reason"):
        op.add_column("agent_runs", sa.Column("fallback_reason", sa.String(length=80), nullable=True))

    if not _has_column("mcp_tool_calls", "error_category"):
        op.add_column("mcp_tool_calls", sa.Column("error_category", sa.String(length=80), nullable=True))


def downgrade() -> None:
    if _has_column("mcp_tool_calls", "error_category"):
        op.drop_column("mcp_tool_calls", "error_category")

    for column_name in [
        "fallback_reason",
        "max_steps",
        "steps_used",
        "estimated_cost_usd",
        "total_tokens",
        "output_tokens",
        "input_tokens",
        "model_name",
        "llm_provider",
        "execution_mode",
    ]:
        if _has_column("agent_runs", column_name):
            op.drop_column("agent_runs", column_name)
