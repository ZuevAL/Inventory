"""Add warehouse orders, picking progress and scan history."""

from alembic import op
import sqlalchemy as sa


revision = "eb4a2b36f977"
down_revision = "d94281e6ac03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(80), nullable=False, unique=True),
        sa.Column("customer", sa.String(255), nullable=False),
    )
    op.create_table(
        "warehouse_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("warehouse_orders.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("picked", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("order_id", "product_id", name="uq_warehouse_order_product"),
        sa.CheckConstraint("quantity > 0 AND picked >= 0 AND picked <= quantity", name="ck_warehouse_line_quantity"),
    )
    op.create_index("ix_warehouse_order_lines_product_id", "warehouse_order_lines", ["product_id"])
    op.create_table(
        "warehouse_operations",
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(7), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("product_code", sa.String(), nullable=False),
        sa.Column("shelf_id", sa.Integer(), nullable=False),
        sa.Column("shelf_label", sa.String(), nullable=False),
        sa.Column("shelf_code", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_line_id", sa.Integer(), sa.ForeignKey("warehouse_order_lines.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_warehouse_operation_quantity"),
        sa.CheckConstraint(
            "(kind = 'pick' AND order_line_id IS NOT NULL) OR "
            "(kind = 'putaway' AND order_line_id IS NULL)",
            name="ck_warehouse_operation_kind",
        ),
    )
    op.create_index("ix_warehouse_operations_created_at", "warehouse_operations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_warehouse_operations_created_at", table_name="warehouse_operations")
    op.drop_table("warehouse_operations")
    op.drop_index("ix_warehouse_order_lines_product_id", table_name="warehouse_order_lines")
    op.drop_table("warehouse_order_lines")
    op.drop_table("warehouse_orders")
