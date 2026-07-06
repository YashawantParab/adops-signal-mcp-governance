"""Create the AdOps Signal production schema.

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01
"""
from alembic import op

from app.database import Base
from app.models import entities  # noqa: F401

revision = "20260701_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
