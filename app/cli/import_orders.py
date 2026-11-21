import argparse
import asyncio
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.warehouse import WarehouseOrder, WarehouseOrderLine
from app.services.warehouse import MAX_STOCK, warehouse_insert, warehouse_write


@dataclass
class ImportedOrder:
    customer: str
    quantities: dict[str, int] = field(default_factory=dict)


def read_orders(source: TextIO) -> dict[str, ImportedOrder]:
    reader = csv.DictReader(source, strict=True)
    columns = {"order_number", "customer", "product_barcode", "quantity"}
    fieldnames = reader.fieldnames or []
    if len(fieldnames) != len(columns) or set(fieldnames) != columns:
        raise ValueError("Столбцы CSV: order_number, customer, product_barcode, quantity")

    orders: dict[str, ImportedOrder] = {}
    for row in reader:
        location = f"Строка CSV {reader.line_num}"
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError(f"{location}: заполните все четыре столбца")
        number, customer, barcode, raw_quantity = (row[key].strip() for key in (
            "order_number", "customer", "product_barcode", "quantity",
        ))
        if len(number) > 80 or len(customer) > 255 or len(barcode) > 512:
            raise ValueError(f"{location}: слишком длинный номер, имя клиента или штрихкод")
        if not raw_quantity.isascii() or not raw_quantity.isdecimal() or len(raw_quantity) > 10:
            raise ValueError(f"{location}: количество должно быть целым положительным числом")
        quantity = int(raw_quantity)
        if not 1 <= quantity <= MAX_STOCK:
            raise ValueError(f"{location}: количество должно быть от 1 до {MAX_STOCK}")

        order = orders.setdefault(number, ImportedOrder(customer))
        if order.customer != customer:
            raise ValueError(f"{location}: у заказа {number} указаны разные клиенты")
        if barcode in order.quantities:
            raise ValueError(f"{location}: товар {barcode} повторяется в заказе {number}")
        order.quantities[barcode] = quantity

    if not orders:
        raise ValueError("Файл CSV не содержит строк заказа")
    return orders


async def import_orders(db: AsyncSession, source: TextIO) -> int:
    try:
        orders = read_orders(source)
    except csv.Error as exc:
        raise ValueError(f"Некорректный CSV: {exc}") from exc

    async with warehouse_write(db):
        # Resolve each barcode in a deterministic order so imports share a lock order.
        barcodes = {barcode for order in orders.values() for barcode in order.quantities}
        products = {}
        for barcode in sorted(barcodes):
            product_id = await db.scalar(select(Product.id).where(
                Product.barcode == barcode,
            ).with_for_update(read=True, key_share=True))
            if product_id is None:
                raise ValueError(f"Товар со штрихкодом {barcode} отсутствует в справочнике")
            products[barcode] = product_id

        # Keep matching orders in the same lock order for concurrently imported files.
        for number, order in sorted(orders.items()):
            insert = warehouse_insert(db, WarehouseOrder).values(
                number=number, customer=order.customer,
            ).on_conflict_do_nothing(index_elements=[WarehouseOrder.number]).returning(WarehouseOrder.id)
            order_id = await db.scalar(insert)
            if order_id is None:
                raise ValueError(f"Заказ {number} уже существует")
            db.add_all(WarehouseOrderLine(order_id=order_id, product_id=products[barcode], quantity=quantity)
                       for barcode, quantity in order.quantities.items())
    return len(orders)


async def import_file(path: Path) -> int:
    try:
        async with AsyncSessionLocal() as db:
            with path.open(encoding="utf-8-sig", newline="") as source:
                return await import_orders(db, source)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт складских заказов из CSV")
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    try:
        count = asyncio.run(import_file(args.csv))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Ошибка: {exc}\n")
    print(f"Импортировано заказов: {count}")


if __name__ == "__main__":
    main()
