"""Add recommendation decision provenance.

Revision ID: 20260703_0002
Revises: 20260701_0001
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_0002"
down_revision = "20260701_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("recommendations")}

    if "decision_reason" not in columns:
        op.add_column("recommendations", sa.Column("decision_reason", sa.Text(), nullable=True))
    if "decided_at" not in columns:
        op.add_column("recommendations", sa.Column("decided_at", sa.DateTime(), nullable=True))
    if "decided_by_user_id" not in columns:
        op.add_column("recommendations", sa.Column("decided_by_user_id", sa.Integer(), nullable=True))
        if bind.dialect.name == "postgresql":
            op.create_foreign_key(
                "fk_recommendations_decided_by_user_id",
                "recommendations",
                "users",
                ["decided_by_user_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("recommendations")}
    if "decided_by_user_id" in columns:
        if bind.dialect.name == "postgresql":
            op.drop_constraint("fk_recommendations_decided_by_user_id", "recommendations", type_="foreignkey")
        op.drop_column("recommendations", "decided_by_user_id")
    if "decided_at" in columns:
        op.drop_column("recommendations", "decided_at")
    if "decision_reason" in columns:
        op.drop_column("recommendations", "decision_reason")
