from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models import Product as ProductModel
from app.schemas import SchemaProduct
from app.models.shelf_stock import ShelfStock as ShelfStockModel

router = APIRouter(prefix="/products", tags=['Продукты'])

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
async def read_products(db: AsyncSession = Depends(get_db)):
    query = select(ProductModel).order_by(ProductModel.id).limit(5)
    result = await db.execute(query)
    products = result.scalars().all()
    return products


@router.delete("/")
async def delete_product(barcode:str, db: AsyncSession = Depends(get_db)):
    query = select(ProductModel).where(ProductModel.barcode == barcode)
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if product is None :
        raise HTTPException(status_code=404, detail="Товар не найден")

    await db.execute(delete(ShelfStockModel).where(ShelfStockModel.product_id == product.id))
    
    await db.delete(product)
    await db.commit()


@router.post("/del_any")
async def delete_product_form(
    barcode: Annotated[str ,Form()],
    db:AsyncSession = Depends(get_db)
):
    return await delete_product(barcode, db)