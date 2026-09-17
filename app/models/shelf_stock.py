from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ShelfStock(Base):
    __tablename__ = "shelf_stock"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    shelf_id: Mapped[int] = mapped_column(ForeignKey("shelves.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("product_id", "shelf_id"),
    )