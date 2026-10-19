from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import require_admin
from app.schemas.users import UserCreate, UserCreateResponse, UserRead
from app.models.user import User
from app.services.auth import AuthContext, reset_password
from app.services.users import UserLoginAlreadyExists, create_user

router = APIRouter(prefix="/users", tags=["Пользователи"], dependencies=[Depends(require_admin)])


@router.get("/", response_model=list[UserRead])
async def list_users(
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.scalars(select(User).order_by(User.id).offset(offset).limit(limit))
    return list(result)


@router.post("/", response_model=UserCreateResponse, status_code=201)
async def create_user_endpoint(data: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await create_user(data, db)
    except UserLoginAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="Логин уже занят") from exc


@router.post("/{user_id}/reset-password", response_model=UserCreateResponse)
async def reset_user_password(
    user_id: int, context: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    return await reset_password(context, user_id, db)
