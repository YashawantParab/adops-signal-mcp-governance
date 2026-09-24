"""Add proposed_actions/action_executions/action_verifications/action_rollbacks
tables for the closed synthetic action loop (Phase 3).

Revision ID: 20260924_0007
Revises: 20260924_0006
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0007"
down_revision = "20260924_0006"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("proposed_actions"):
        op.create_table(
            "proposed_actions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
            sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
            sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id"), nullable=True),
            sa.Column("action_type", sa.String(length=60), nullable=False),
            sa.Column("requested_params", sa.JSON(), nullable=False),
            sa.Column("risk_class", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="proposed"),
            sa.Column("proposed_by", sa.String(length=80), nullable=False),
            sa.Column("state_version", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_proposed_actions_campaign_id", "proposed_actions", ["campaign_id"])

    if not _has_table("action_executions"):
        op.create_table(
            "action_executions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("proposed_action_id", sa.Integer(), sa.ForeignKey("proposed_actions.id"), nullable=False),
            sa.Column("executed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("before_state", sa.JSON(), nullable=False),
            sa.Column("after_state", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("executed_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_action_executions_proposed_action_id", "action_executions", ["proposed_action_id"])

    if not _has_table("action_verifications"):
        op.create_table(
            "action_verifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("action_execution_id", sa.Integer(), sa.ForeignKey("action_executions.id"), nullable=False),
            sa.Column("expected_state", sa.JSON(), nullable=False),
            sa.Column("actual_state", sa.JSON(), nullable=False),
            sa.Column("verification_status", sa.String(length=40), nullable=False),
            sa.Column("mismatch_reason", sa.Text(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_action_verifications_action_execution_id", "action_verifications", ["action_execution_id"])

    if not _has_table("action_rollbacks"):
        op.create_table(
            "action_rollbacks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("action_execution_id", sa.Integer(), sa.ForeignKey("action_executions.id"), nullable=False),
            sa.Column("rolled_back_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("restored_state", sa.JSON(), nullable=False),
            sa.Column("actual_state_after", sa.JSON(), nullable=False),
            sa.Column("verification_status", sa.String(length=40), nullable=False),
            sa.Column("rolled_back_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_action_rollbacks_action_execution_id", "action_rollbacks", ["action_execution_id"])


def downgrade() -> None:
    for table_name, index_name in [
        ("action_rollbacks", "ix_action_rollbacks_action_execution_id"),
        ("action_verifications", "ix_action_verifications_action_execution_id"),
        ("action_executions", "ix_action_executions_proposed_action_id"),
        ("proposed_actions", "ix_proposed_actions_campaign_id"),
    ]:
        if _has_table(table_name):
            op.drop_index(index_name, table_name=table_name)
            op.drop_table(table_name)
