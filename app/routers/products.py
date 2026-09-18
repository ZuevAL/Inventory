from fastapi import APIRouter, Depends
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.product import Product as ProductModel
from app.schemas.products import SchemaProduct


router = APIRouter(prefix="/products")

@router.post("/")
async def create_product(product: SchemaProduct, db: AsyncSession = Depends(get_db)):
    db_product = ProductModel(name = product.name, barcode = product.barcode)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return product


@router.get("/")
async def read_products(db: AsyncSession = Depends(get_db)):
    query = select(ProductModel).order_by(ProductModel.id).limit(5)
    result = await db.execute(query)
    products = result.scalars().all()
    return products