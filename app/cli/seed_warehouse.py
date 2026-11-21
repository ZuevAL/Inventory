import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.shelf import Shelf
from app.models.shelf_stock import ShelfStock
from app.models.warehouse import WarehouseOrder, WarehouseOrderLine
from app.services.warehouse import warehouse_write


async def seed_warehouse(db: AsyncSession) -> bool:
    cable = Product(name="Кабель USB‑C", barcode="4601234567893")
    adapter = Product(name="Адаптер питания 20 Вт", barcode="4601234567909")
    holder = Product(name="Держатель кабеля", barcode="4601234567916")
    shelf_a = Shelf(code="A-01-01")
    shelf_b = Shelf(code="A-01-02")
    shelf_c = Shelf(code="B-02-01")
    first = WarehouseOrder(number="ЗК-1042", customer="Север Маркет")
    second = WarehouseOrder(number="ЗК-1043", customer="Офис Плюс")

    async with warehouse_write(db):
        existing = (await db.scalars(select(WarehouseOrder.number).where(
            WarehouseOrder.number.in_([first.number, second.number]),
        ))).all()
        if len(existing) == 2:
            return False
        matching_product = await db.scalar(select(Product.id).where(Product.barcode.in_([
            cable.barcode, adapter.barcode, holder.barcode,
        ])).limit(1))
        matching_shelf = await db.scalar(select(Shelf.id).where(Shelf.code.in_([
            shelf_a.code, shelf_b.code, shelf_c.code,
        ])).limit(1))
        if existing or matching_product is not None or matching_shelf is not None:
            raise ValueError("Демонстрационные коды уже используются. Выберите отдельную базу данных")

        db.add_all([cable, adapter, holder, shelf_a, shelf_b, shelf_c, first, second])
        await db.flush()
        db.add_all([
            ShelfStock(product_id=cable.id, shelf_id=shelf_a.id, quantity=12),
            ShelfStock(product_id=cable.id, shelf_id=shelf_b.id, quantity=5),
            ShelfStock(product_id=adapter.id, shelf_id=shelf_b.id, quantity=8),
            ShelfStock(product_id=holder.id, shelf_id=shelf_c.id, quantity=24),
            WarehouseOrderLine(order_id=first.id, product_id=cable.id, quantity=3),
            WarehouseOrderLine(order_id=first.id, product_id=adapter.id, quantity=2),
            WarehouseOrderLine(order_id=second.id, product_id=holder.id, quantity=4),
        ])
    return True


async def seed_from_settings() -> bool:
    try:
        async with AsyncSessionLocal() as db:
            return await seed_warehouse(db)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Добавить демонстрационные товары, полки и заказы")
    parser.parse_args()
    try:
        added = asyncio.run(seed_from_settings())
    except ValueError as exc:
        parser.exit(1, f"Ошибка: {exc}\n")
    print("Демонстрационные данные добавлены." if added else "Демонстрационные заказы уже присутствуют.")


if __name__ == "__main__":
    main()
