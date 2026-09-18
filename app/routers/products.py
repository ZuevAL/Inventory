from fastapi import APIRouter, Depends
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product as ProductModel
from app.schemas.products import SchemaProduct


router = APIRouter(prefix="/products")

@router.post("/")
async def create_product(product: SchemaProduct,
    db: AsyncSession = Depends(get_db)):
    db_product= ProductModel(name = product.name, barcode = product.barcode)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product