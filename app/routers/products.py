from fastapi import APIRouter, Depends
from app.db import get_db
from app import models, schemas
router = APIRouter(prefix="/products")

@router.post("/")
async def create_product(
    product: schemas.Product
    db: AsyncSession = Depends(get_db)
):
    db_product= models.Product(name = product.name, barcode = product.barcode)