from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.product import Product as ProductModel
from app.models.shelf import Shelf as ShelfModel
from app.models.shelf_stock import ShelfStock as ShelfStockModel
from app.schemas.shelf_stock import SchemaShelfStock
from app.dependencies import get_current_auth, require_admin
from app.services.warehouse import MAX_STOCK, warehouse_insert, warehouse_write


router = APIRouter(prefix="/stock", tags=['Наличие товаров'], dependencies=[Depends(get_current_auth)])

@router.post("/")
async def create_stock(stock: SchemaShelfStock, db: AsyncSession = Depends(get_db)):
    if not 0 <= stock.quantity <= MAX_STOCK:
        raise HTTPException(422, "Недопустимое количество товара")
    async with warehouse_write(db):
        product_id = await db.scalar(select(ProductModel.id).where(
            ProductModel.barcode == stock.product_barcode,
        ).with_for_update(read=True, key_share=True))
        if product_id is None:
            raise HTTPException(404, "Продукт не найден")

        shelf_id = await db.scalar(select(ShelfModel.id).where(ShelfModel.code == stock.shelf_code))
        if shelf_id is None:
            raise HTTPException(404, "Полка не найдена")

        insert = warehouse_insert(db, ShelfStockModel).values(
            product_id=product_id, shelf_id=shelf_id, quantity=stock.quantity,
        ).on_conflict_do_nothing(
            index_elements=[ShelfStockModel.product_id, ShelfStockModel.shelf_id],
        ).returning(ShelfStockModel)
        row = await db.scalar(insert)
        if row is None:
            raise HTTPException(409, "Товар уже добавлен на эту полку")
        return row


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
async def read_stock(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 5,
    db: AsyncSession = Depends(get_db),
):
    # UI needs product and shelf names, not just foreign keys.
    query = (
        select(
            ShelfStockModel.id,
            ShelfStockModel.product_id,
            ShelfStockModel.shelf_id,
            ProductModel.name.label("product_name"),
            ProductModel.barcode.label("product_barcode"),
            ShelfModel.code.label("shelf_code"),
            ShelfStockModel.quantity,
        )
        .join(ProductModel, ProductModel.id == ShelfStockModel.product_id)
        .join(ShelfModel, ShelfModel.id == ShelfStockModel.shelf_id)
        .order_by(ShelfStockModel.id)
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return [dict(row) for row in result.mappings().all()]

@router.delete("/", dependencies=[Depends(require_admin)])
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

    if product is None:
        raise HTTPException(status_code=404, detail="Товар на этой полке не найден")

    await db.delete(product)
    await db.commit()


@router.post("/delete-form", dependencies=[Depends(require_admin)])
async def delete_from_shelf_form(
    barcode: Annotated [str, Form()],
    shelf_code:Annotated [str, Form()],
    db :AsyncSession = Depends(get_db)):
    return await delete_product_by_barcode(barcode, shelf_code,db)


@router.patch("/")
async def update_quantity_in_shelves(barcode:str, shelf_code:str, adding:int,
                                      db: AsyncSession =Depends (get_db)):
    if not -MAX_STOCK <= adding <= MAX_STOCK:
        raise HTTPException(409, "Недопустимое изменение количества товара")
    product_id = select(ProductModel.id).where(ProductModel.barcode == barcode).scalar_subquery()
    shelf_id = select(ShelfModel.id).where(ShelfModel.code == shelf_code).scalar_subquery()
    stock = (ShelfStockModel.product_id == product_id, ShelfStockModel.shelf_id == shelf_id)
    async with warehouse_write(db):
        updated_id = await db.scalar(update(ShelfStockModel).where(
            *stock, ShelfStockModel.quantity >= -adding, ShelfStockModel.quantity <= MAX_STOCK - adding,
        ).values(quantity=ShelfStockModel.quantity + adding).returning(ShelfStockModel.id))
        if updated_id is None:
            if await db.scalar(select(ShelfStockModel.id).where(*stock)) is None:
                raise HTTPException(404, "Товар не найден")
            raise HTTPException(409, "Изменение выводит остаток на полке за допустимые пределы")


@router.post("/patch-form")
async def update_quantity_form(
    barcode:Annotated[str,Form()],
    shelf_code:Annotated[ str, Form()],
    adding: Annotated[int, Form()],
    db: AsyncSession = Depends(get_db)
):
    return await update_quantity_in_shelves(barcode, shelf_code, adding, db)
