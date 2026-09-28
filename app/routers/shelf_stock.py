from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
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
    query = select(ProductModel).where(ProductModel.barcode == stock.product_barcode)
    result = await db.execute(query)
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    query = select(ShelfModel).where(ShelfModel.code == stock.shelf_code)
    result = await db.execute(query)
    shelf = result.scalar_one_or_none()
    if shelf is None:
        raise HTTPException(status_code=404, detail="Полка не найдена")

    db_stock = ShelfStockModel(product_id=product.id, shelf_id=shelf.id, quantity=stock.quantity)
    db.add(db_stock)
    await db.commit()
    await db.refresh(db_stock)
    return db_stock


@router.post("/form")
async def create_stock_form(
    product_barcode: Annotated[str, Form()],
    shelf_code: Annotated[str, Form()],
    quantity: Annotated[int, Form()],
    db: AsyncSession = Depends(get_db),
):
    stock = SchemaShelfStock(
        product_barcode=product_barcode,
        shelf_code=shelf_code,
        quantity=quantity,
    )
    return await create_stock(stock, db)


@router.get("/")
async def read_stock(db: AsyncSession = Depends(get_db)):
    query = select(ShelfStockModel).order_by(ShelfStockModel.id).limit(5)
    result = await db.execute(query)
    stock = result.scalars().all()
    return stock

@router.delete("/")
async def delete_product_by_barcode(barcode:str ,shelf_code:str, db :AsyncSession = Depends(get_db)):
    del_id = await db.scalar(select(ProductModel.id).where(ProductModel.barcode == barcode))
    shelf_id  =await db.scalar(select(ShelfModel.id).where(ShelfModel.code==shelf_code))
    query = select(ShelfStockModel).where(ShelfStockModel.product_id == del_id, ShelfStockModel.shelf_id == shelf_id)
    result = await db.execute(query)
    product = result.scalar_one_or_none()

    if del_id is None:
        raise HTTPException(status_code=404, detail="Товар с таким barcode не найден")

    if shelf_id is None:
        raise HTTPException(status_code=404, detail="Полка с таким кодом не найдена")

    await db.delete(product)
    await db.commit()


@router.post("/delete-form")
async def delete_from_shelf_form(
    barcode: Annotated [str, Form()],
    shelf_code:Annotated [str, Form()],
    db :AsyncSession = Depends(get_db)):
    return await delete_product_by_barcode(barcode, shelf_code,db)


@router.patch("/")
async def update_quantity_in_shelves(barcode:str, shelf_code:str, adding:int,
                                      db: AsyncSession =Depends (get_db)):
    changing_product = await db.scalar(select(ProductModel.id).where(ProductModel.barcode == barcode))
    changing_shelf = await db.scalar(select(ShelfModel.id).where(ShelfModel.code == shelf_code))
    query = select(ShelfStockModel).where(ShelfStockModel.shelf_id == changing_shelf, \
                                          ShelfStockModel.product_id == changing_product)
    result = await db.execute(query)
    product = result.scalar_one_or_none()

    if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")


    product.quantity += adding
    await db.commit()


@router.post("/patch-form")
async def update_quantity_form(
    barcode:Annotated[str,Form()],
    shelf_code:Annotated[ str, Form()],
    adding: Annotated[int, Form()],
    db: AsyncSession = Depends(get_db)
):
    return await update_quantity_in_shelves(barcode, shelf_code, adding, db)

