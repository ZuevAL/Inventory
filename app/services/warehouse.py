from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.shelf import Shelf
from app.models.shelf_stock import ShelfStock
from app.models.warehouse import WarehouseOperation, WarehouseOrder, WarehouseOrderLine
from app.schemas.warehouse import (
    OperationRead, OperationRequest, WarehouseLineRead, WarehouseOrderRead,
    WarehouseProductRead, WarehouseShelfRead, WarehouseSnapshot, WarehouseStockRead,
)

MAX_STOCK = 2_147_483_647


@asynccontextmanager
async def warehouse_write(db: AsyncSession):
    # Authentication may already have opened a read transaction on this session.
    if db.in_transaction():
        await db.rollback()
    async with db.begin():
        if db.get_bind().dialect.name == "sqlite":
            # Take the writer lock before reads so stock decisions have a current view.
            await db.execute(text("BEGIN IMMEDIATE"))
        yield


def warehouse_insert(db: AsyncSession, model):
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else postgresql_insert
    return insert(model)


async def get_snapshot(db: AsyncSession) -> WarehouseSnapshot:
    if db.in_transaction():
        await db.rollback()
    async with db.begin():
        if db.get_bind().dialect.name == "sqlite":
            await db.execute(text("BEGIN"))
        else:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

        products = await db.scalars(select(Product).order_by(Product.name, Product.id))
        shelves = await db.scalars(select(Shelf).order_by(Shelf.code, Shelf.id))
        stock = await db.scalars(select(ShelfStock).where(ShelfStock.quantity > 0).order_by(ShelfStock.id))
        orders = await db.scalars(select(WarehouseOrder).order_by(WarehouseOrder.id))
        lines = await db.scalars(select(WarehouseOrderLine).order_by(WarehouseOrderLine.id))
        operations = await db.scalars(select(WarehouseOperation).order_by(
            WarehouseOperation.created_at.desc(), WarehouseOperation.operation_id,
        ).limit(30))

        lines_by_order = defaultdict(list)
        for line in lines:
            lines_by_order[line.order_id].append(WarehouseLineRead.model_validate(line))

        return WarehouseSnapshot(
            products=[WarehouseProductRead(id=p.id, name=p.name, barcodes=[p.barcode]) for p in products],
            shelves=[WarehouseShelfRead(id=s.id, code=s.code, qr=f"shelf:{s.id}") for s in shelves],
            stock=[WarehouseStockRead.model_validate(row) for row in stock],
            orders=[WarehouseOrderRead(
                id=order.id, number=order.number, customer=order.customer, lines=lines_by_order[order.id],
            ) for order in orders],
            operations=[OperationRead.model_validate(row) for row in operations],
        )


def read_replay(operation: WarehouseOperation, data: OperationRequest, user_id: int) -> OperationRead:
    previous_request = (
        operation.kind, operation.product_code, operation.shelf_code,
        operation.quantity, operation.order_line_id, operation.user_id,
    )
    current_request = (
        data.kind, data.product_code, data.shelf_code,
        data.quantity, data.order_line_id, user_id,
    )
    if previous_request != current_request:
        raise HTTPException(409, "Идентификатор уже использован для другой операции")
    return OperationRead.model_validate(operation)


async def apply_operation(db: AsyncSession, data: OperationRequest, user_id: int) -> OperationRead:
    operation_id = str(data.operation_id)
    async with warehouse_write(db):
        previous = await db.get(WarehouseOperation, operation_id)
        if previous is not None:
            return read_replay(previous, data, user_id)

        product = await db.scalar(select(Product).where(
            Product.barcode == data.product_code,
        ).with_for_update(read=True, key_share=True))
        if product is None:
            raise HTTPException(404, "Товар с таким штрихкодом не найден")

        shelf = await find_shelf(db, data.shelf_code)
        if shelf is None:
            raise HTTPException(404, "Полка не найдена")

        if data.kind == "pick":
            line = await db.get(WarehouseOrderLine, data.order_line_id)
            if line is None:
                raise HTTPException(404, "Строка заказа не найдена")
            if line.product_id != product.id:
                raise HTTPException(409, "Отсканированный товар не соответствует строке заказа")

        # Reserve the UUID before changing inventory. The row rolls back on any later error.
        reservation = warehouse_insert(db, WarehouseOperation).values(
            operation_id=operation_id,
            kind=data.kind,
            product_id=product.id,
            product_name=product.name,
            product_code=data.product_code,
            shelf_id=shelf.id,
            shelf_label=shelf.code,
            shelf_code=data.shelf_code,
            quantity=data.quantity,
            order_line_id=data.order_line_id,
            user_id=user_id,
            created_at=datetime.now(UTC),
        ).on_conflict_do_nothing(index_elements=[WarehouseOperation.operation_id]).returning(WarehouseOperation)
        operation = await db.scalar(reservation)
        if operation is None:
            return read_replay(await db.get(WarehouseOperation, operation_id), data, user_id)

        if data.kind == "putaway":
            await add_stock(db, product.id, shelf.id, data.quantity)
        else:
            await pick_stock(db, product.id, shelf.id, data.order_line_id, data.quantity)
        return OperationRead.model_validate(operation)


async def find_shelf(db: AsyncSession, code: str) -> Shelf | None:
    display_code = Shelf.code == code
    statement = select(Shelf).where(display_code)
    prefix, _, label = code.partition(":")
    if prefix == "shelf" and label.isascii() and label.isdecimal() and not label.startswith("0") and len(label) <= 18:
        # Prefer an exact generated label if a legacy display code equals that label.
        qr_code = Shelf.id == int(label)
        statement = select(Shelf).where(or_(qr_code, display_code)).order_by(qr_code.desc()).limit(1)
    return await db.scalar(statement.with_for_update(read=True, key_share=True))


async def add_stock(db: AsyncSession, product_id: int, shelf_id: int, quantity: int) -> None:
    operation = warehouse_insert(db, ShelfStock).values(
        product_id=product_id, shelf_id=shelf_id, quantity=quantity,
    ).on_conflict_do_update(
        index_elements=[ShelfStock.product_id, ShelfStock.shelf_id],
        set_={"quantity": ShelfStock.quantity + quantity},
        where=ShelfStock.quantity <= MAX_STOCK - quantity,
    ).returning(ShelfStock.id)
    if await db.scalar(operation) is None:
        raise HTTPException(409, "На полке достигнут предельный остаток товара")


async def pick_stock(db: AsyncSession, product_id: int, shelf_id: int, line_id: int, quantity: int) -> None:
    picked = await db.scalar(update(WarehouseOrderLine).where(
        WarehouseOrderLine.id == line_id,
        WarehouseOrderLine.quantity - WarehouseOrderLine.picked >= quantity,
    ).values(picked=WarehouseOrderLine.picked + quantity).returning(WarehouseOrderLine.id))
    if picked is None:
        raise HTTPException(409, "Количество превышает остаток к сборке по строке заказа")

    stock = await db.scalar(update(ShelfStock).where(
        ShelfStock.product_id == product_id,
        ShelfStock.shelf_id == shelf_id,
        ShelfStock.quantity >= quantity,
    ).values(quantity=ShelfStock.quantity - quantity).returning(ShelfStock.id))
    if stock is None:
        raise HTTPException(409, "На этой полке недостаточно товара")
