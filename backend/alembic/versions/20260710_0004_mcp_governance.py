"""Add MCP governance persistence tables.

Revision ID: 20260710_0004
Revises: 20260703_0003
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "20260710_0004"
down_revision = "20260703_0003"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("agent_runs"):
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_query", sa.Text(), nullable=False),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("risk_level", sa.String(length=40), nullable=False),
            sa.Column("risk_score", sa.Float(), nullable=False),
            sa.Column("final_recommendation", sa.Text(), nullable=False),
            sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )

    if not _has_table("mcp_tool_calls"):
        op.create_table(
            "mcp_tool_calls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=False),
            sa.Column("input_json", sa.JSON(), nullable=False),
            sa.Column("output_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("approval_requests"):
        op.create_table(
            "approval_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
            sa.Column("proposed_action", sa.Text(), nullable=False),
            sa.Column("risk_score", sa.Float(), nullable=False),
            sa.Column("risk_level", sa.String(length=40), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("policy_checks"):
        op.create_table(
            "policy_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
            sa.Column("policy_name", sa.String(length=160), nullable=False),
            sa.Column("result", sa.String(length=40), nullable=False),
            sa.Column("matched_rules", sa.JSON(), nullable=False),
            sa.Column("citation", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("blocked_actions"):
        op.create_table(
            "blocked_actions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("risk_level", sa.String(length=40), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    for table_name in [
        "blocked_actions",
        "policy_checks",
        "approval_requests",
        "mcp_tool_calls",
        "agent_runs",
    ]:
        if _has_table(table_name):
            op.drop_table(table_name)
