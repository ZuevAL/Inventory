from fastapi import APIRouter, Depends
from app.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.shelf import Shelf as ShelfModel
from app.schemas.shelves import SchemaShelves


router = APIRouter(prefix="/shelves")

@router.post("/")
async def create_shelf(shelf: SchemaShelves, db: AsyncSession = Depends(get_db)):
    db_shelf = ShelfModel(code = shelf.code)
    db.add(db_shelf)
    await db.commit()
    await db.refresh(db_shelf)
    return db_shelf


@router.get("/")
async def read_shelves(db: AsyncSession = Depends(get_db)):
    query = select(ShelfModel).order_by(ShelfModel.id).limit(5)
    result = await db.execute(query)
    shelves = result.scalars().all()
    return shelves