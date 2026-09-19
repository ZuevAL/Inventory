from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.product import Product as ProductModel
from app.models.shelf import Shelf as ShelfModel
from app.models.shelf_stock import ShelfStock as ShelfStockModel
from app.schemas.shelf_stock import SchemaShelfStock


router = APIRouter(prefix="/stock", tags=['Наличие товаров'])

@router.post("/")
async def create_stock(stock: SchemaShelfStock, db: AsyncSession = Depends(get_db)):
    product = await db.get(ProductModel, stock.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    shelf = await db.get(ShelfModel, stock.shelf_id)
    if shelf is None:
        raise HTTPException(status_code=404, detail="Полка не найдена")

    db_stock = ShelfStockModel(product_id = stock.product_id, shelf_id = stock.shelf_id, quantity = stock.quantity)
    db.add(db_stock)
    await db.commit()
    await db.refresh(db_stock)
    return db_stock


@router.get("/")
async def read_stock(db: AsyncSession = Depends(get_db)):
    query = select(ShelfStockModel).order_by(ShelfStockModel.id).limit(5)
    result = await db.execute(query)
    stock = result.scalars().all()
    return stock
