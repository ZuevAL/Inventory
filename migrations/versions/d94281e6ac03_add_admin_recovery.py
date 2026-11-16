"""Add saved admin recovery codes, attempt limits and a private audit trail."""

import sqlalchemy as sa
from alembic import op

revision = "d94281e6ac03"
down_revision = "c83170d591a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("recovery_code_hash", sa.String(64)),
        sa.Column("pending_recovery_hash", sa.String(64)),
        sa.Column("pending_recovery_session_id", sa.String(36)),
        sa.Column("pending_recovery_expires_at", sa.Integer()),
    ):
        op.add_column("users", column)
    op.create_table(
        "recovery_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
    )
    op.create_index(
        "ix_recovery_events_occurred_at", "recovery_events", ["occurred_at"]
    )
    op.create_index(
        "ix_recovery_events_user_time", "recovery_events", ["user_id", "occurred_at"]
    )
    op.create_index(
        "ix_recovery_events_source_time", "recovery_events", ["source", "occurred_at"]
    )
    op.create_table(
        "recovery_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_recovery_limits_window_start", "recovery_limits", ["window_start"]
    )


def downgrade() -> None:
    op.drop_table("recovery_limits")
    op.drop_table("recovery_events")
    for column in (
        "pending_recovery_expires_at",
        "pending_recovery_session_id",
        "pending_recovery_hash",
        "recovery_code_hash",
    ):
        op.drop_column("users", column)
