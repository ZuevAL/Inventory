from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import (
    generate_temporary_password,
    hash_password,
)
from app.models.user import User
from app.schemas.users import (
    UserCreate,
    UserCreateResponse,
    UserRead,
)


class UserLoginAlreadyExists(Exception):
    pass


class FirstAdminAlreadyExists(Exception):
    pass


async def create_first_admin(data: UserCreate, db: AsyncSession) -> UserCreateResponse:
    """Local bootstrap only; serialize the check and insert on SQLite."""
    if data.role != "admin":
        raise ValueError("Первый пользователь должен быть администратором")
    if db.in_transaction():
        await db.rollback()
    try:
        await db.execute(text("BEGIN IMMEDIATE"))
        existing_admin_id = await db.scalar(
            select(User.id).where(User.role == "admin").limit(1)
        )
        if existing_admin_id is not None:
            raise FirstAdminAlreadyExists(
                "Администратор уже существует. Другие аккаунты создаются через приложение."
            )
        return await create_user(data, db)
    except BaseException:
        await db.rollback()
        raise


async def create_user(
    data: UserCreate,
    db: AsyncSession,
) -> UserCreateResponse:
    query = select(User.id).where(User.login == data.login)

    existing_user_id = await db.scalar(query)

    if existing_user_id is not None:
        raise UserLoginAlreadyExists("Логин уже занят")

    temporary_password = generate_temporary_password()

    password_hash = await run_in_threadpool(
        hash_password,
        temporary_password,
    )

    user = User(
        login=data.login,
        full_name=data.full_name,
        role=data.role,
        password_hash=password_hash,
        must_change_password=True,
    )

    db.add(user)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()

        existing_user_id = await db.scalar(query)

        if existing_user_id is not None:
            raise UserLoginAlreadyExists(
                "Логин уже занят"
            ) from exc

        raise

    await db.refresh(user)

    return UserCreateResponse(
        user=UserRead.model_validate(user),
        temporary_password=temporary_password,
    )
