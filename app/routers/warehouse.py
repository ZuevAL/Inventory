from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_auth
from app.schemas.warehouse import OperationRead, OperationRequest, WarehouseSnapshot
from app.services.auth import AuthContext
from app.services.warehouse import apply_operation, get_snapshot


router = APIRouter(prefix="/warehouse", tags=["Складские операции"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
WarehouseUser = Annotated[AuthContext, Depends(get_current_auth)]


@router.get("/snapshot", dependencies=[Depends(get_current_auth)])
async def snapshot(db: DatabaseSession) -> WarehouseSnapshot:
    return await get_snapshot(db)


@router.post("/operations")
async def operations(data: OperationRequest, db: DatabaseSession, context: WarehouseUser) -> OperationRead:
    return await apply_operation(db, data, context.user.id)
