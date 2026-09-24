"""Add gate_decisions table and agent_runs client-safe-brief columns (Phase 2).

Revision ID: 20260924_0006
Revises: 20260924_0005
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0006"
down_revision = "20260924_0005"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("agent_runs", "client_safe_brief"):
        op.add_column("agent_runs", sa.Column("client_safe_brief", sa.Text(), nullable=True))
    if not _has_column("agent_runs", "client_safe_brief_status"):
        op.add_column("agent_runs", sa.Column("client_safe_brief_status", sa.String(length=40), nullable=True))

    if not _has_table("gate_decisions"):
        op.create_table(
            "gate_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=True),
            sa.Column("decision_point", sa.String(length=60), nullable=False),
            sa.Column("gate_type", sa.String(length=20), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=True),
            sa.Column("model_name", sa.String(length=120), nullable=True),
            sa.Column("decision", sa.String(length=80), nullable=False),
            sa.Column("probability", sa.Float(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("rule_floor", sa.String(length=40), nullable=True),
            sa.Column("final_decision", sa.String(length=80), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
            sa.Column("input_reference", sa.String(length=120), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("schema_version", sa.String(length=40), nullable=False, server_default="gate-decision-v1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_gate_decisions_agent_run_id", "gate_decisions", ["agent_run_id"])
        op.create_index("ix_gate_decisions_decision_point", "gate_decisions", ["decision_point"])


def downgrade() -> None:
    if _has_table("gate_decisions"):
        op.drop_index("ix_gate_decisions_decision_point", table_name="gate_decisions")
        op.drop_index("ix_gate_decisions_agent_run_id", table_name="gate_decisions")
        op.drop_table("gate_decisions")

    if _has_column("agent_runs", "client_safe_brief_status"):
        op.drop_column("agent_runs", "client_safe_brief_status")
    if _has_column("agent_runs", "client_safe_brief"):
        op.drop_column("agent_runs", "client_safe_brief")
