from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


OperationKind = Literal["putaway", "pick"]
OperationQuantity = Annotated[int, Field(strict=True, ge=1, le=100_000)]
OperationCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    kind: OperationKind
    product_code: OperationCode
    shelf_code: OperationCode
    quantity: OperationQuantity
    order_line_id: Annotated[int, Field(strict=True, gt=0)] | None = None

    @model_validator(mode="after")
    def validate_order_line(self):
        if self.kind == "pick" and self.order_line_id is None:
            raise ValueError("Для сборки укажите строку заказа")
        if self.kind == "putaway" and self.order_line_id is not None:
            raise ValueError("Для раскладки строка заказа не нужна")
        return self


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operation_id: UUID
    kind: OperationKind
    product_id: int
    product_name: str
    shelf_id: int
    shelf_label: str
    quantity: int
    order_line_id: int | None
    user_id: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def use_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class WarehouseProductRead(BaseModel):
    id: int
    name: str
    barcodes: list[str]


class WarehouseShelfRead(BaseModel):
    id: int
    code: str
    qr: str


class WarehouseStockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    shelf_id: int
    quantity: int


class WarehouseLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    picked: int


class WarehouseOrderRead(BaseModel):
    id: int
    number: str
    customer: str
    lines: list[WarehouseLineRead]


class WarehouseSnapshot(BaseModel):
    products: list[WarehouseProductRead]
    shelves: list[WarehouseShelfRead]
    stock: list[WarehouseStockRead]
    orders: list[WarehouseOrderRead]
    operations: list[OperationRead]
