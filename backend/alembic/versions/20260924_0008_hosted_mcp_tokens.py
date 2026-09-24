"""Add mcp_access_tokens and external_mcp_calls for the hosted, authenticated,
read-only external MCP endpoint (Phase 3F).

Revision ID: 20260924_0008
Revises: 20260924_0007
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0008"
down_revision = "20260924_0007"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("mcp_access_tokens"):
        op.create_table(
            "mcp_access_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("scope", sa.String(length=40), nullable=False, server_default="read"),
            sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_mcp_access_tokens_token_hash", "mcp_access_tokens", ["token_hash"], unique=True)

    if not _has_table("external_mcp_calls"):
        op.create_table(
            "external_mcp_calls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token_id", sa.Integer(), sa.ForeignKey("mcp_access_tokens.id"), nullable=True),
            sa.Column("method", sa.String(length=80), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("client_host", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_external_mcp_calls_token_id", "external_mcp_calls", ["token_id"])


def downgrade() -> None:
    if _has_table("external_mcp_calls"):
        op.drop_index("ix_external_mcp_calls_token_id", table_name="external_mcp_calls")
        op.drop_table("external_mcp_calls")
    if _has_table("mcp_access_tokens"):
        op.drop_index("ix_mcp_access_tokens_token_hash", table_name="mcp_access_tokens")
        op.drop_table("mcp_access_tokens")
