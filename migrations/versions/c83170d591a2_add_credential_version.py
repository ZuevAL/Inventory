"""Bind tokens to the current password version.

Revision ID: c83170d591a2
Revises: a50fc9e36bfe
"""
from alembic import op
import sqlalchemy as sa

revision = "c83170d591a2"
down_revision = "a50fc9e36bfe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("credential_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "credential_version")
