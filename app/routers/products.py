from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models import Product as ProductModel
from app.schemas.products import SchemaProduct
from app.models.shelf_stock import ShelfStock as ShelfStockModel
from app.models.warehouse import WarehouseOrderLine
from app.dependencies import get_current_auth, require_admin
from app.services.warehouse import warehouse_write

router = APIRouter(prefix="/products", tags=['Продукты'], dependencies=[Depends(get_current_auth)])

@router.post("/")
async def create_product(product: SchemaProduct, db: AsyncSession = Depends(get_db)):
    db_product = ProductModel(name = product.name, barcode = product.barcode)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return product


@router.post("/form")
async def create_product_form(
    name: Annotated[str, Form()],
    barcode: Annotated[str, Form()],
    db: AsyncSession = Depends(get_db),
):
    return await create_product(SchemaProduct(name=name, barcode=barcode), db)


@router.get("/")
async def read_products(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 5,
    db: AsyncSession = Depends(get_db),
):
    query = select(ProductModel).order_by(ProductModel.id).offset(offset).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()
    return products


@router.delete("/", dependencies=[Depends(require_admin)])
async def delete_product(barcode:str, db: AsyncSession = Depends(get_db)):
    async with warehouse_write(db):
        product = await db.scalar(select(ProductModel).where(ProductModel.barcode == barcode).with_for_update())
        if product is None:
            raise HTTPException(404, "Товар не найден")
        if await db.scalar(select(WarehouseOrderLine.id).where(
            WarehouseOrderLine.product_id == product.id,
        ).limit(1)) is not None:
            raise HTTPException(409, "Товар используется в заказах")
        await db.execute(delete(ShelfStockModel).where(ShelfStockModel.product_id == product.id))
        await db.delete(product)


@router.post("/del_any", dependencies=[Depends(require_admin)])
async def delete_product_form(
    barcode: Annotated[str ,Form()],
    db:AsyncSession = Depends(get_db)
):
    return await delete_product(barcode, db)
