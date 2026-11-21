from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WarehouseOrder(Base):
    __tablename__ = "warehouse_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(80), unique=True)
    customer: Mapped[str] = mapped_column(String(255))


class WarehouseOrderLine(Base):
    __tablename__ = "warehouse_order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_warehouse_order_product"),
        CheckConstraint("quantity > 0 AND picked >= 0 AND picked <= quantity", name="ck_warehouse_line_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("warehouse_orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int]
    picked: Mapped[int] = mapped_column(default=0, server_default="0")


class WarehouseOperation(Base):
    __tablename__ = "warehouse_operations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_warehouse_operation_quantity"),
        CheckConstraint(
            "(kind = 'pick' AND order_line_id IS NOT NULL) OR "
            "(kind = 'putaway' AND order_line_id IS NULL)",
            name="ck_warehouse_operation_kind",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(7))
    # Store the display labels and codes as they were at the time of the operation.
    product_id: Mapped[int]
    product_name: Mapped[str]
    product_code: Mapped[str]
    shelf_id: Mapped[int]
    shelf_label: Mapped[str]
    shelf_code: Mapped[str]
    quantity: Mapped[int]
    order_line_id: Mapped[int | None] = mapped_column(ForeignKey("warehouse_order_lines.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
