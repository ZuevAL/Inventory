import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.core.security import verify_password
from app.models.user import User
from app.schemas.users import UserCreate
from app.services.users import (
    UserLoginAlreadyExists,
    create_user,
)


@pytest.mark.parametrize("role", ["worker", "admin"])
def test_create_user(role):
    asyncio.run(_check_create_user(role))


async def _check_create_user(role):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )

        async with session_factory() as db:
            data = UserCreate(
                login="Worker_01",
                full_name="Иван Петров",
                role=role,
            )

            result = await create_user(data, db)

            stored_user = await db.scalar(
                select(User).where(User.id == result.user.id)
            )

            assert stored_user is not None
            assert stored_user.login == "worker_01"
            assert stored_user.role == role
            assert stored_user.must_change_password is True

            assert len(result.temporary_password) == 16
            assert stored_user.password_hash != result.temporary_password

            assert verify_password(
                result.temporary_password,
                stored_user.password_hash,
            )

            assert "password_hash" not in result.user.model_dump()

            duplicate = UserCreate(
                login="WORKER_01",
                full_name="Другой пользователь",
                role=role,
            )

            with pytest.raises(UserLoginAlreadyExists):
                await create_user(duplicate, db)

            user_count = await db.scalar(
                select(func.count()).select_from(User)
            )

            assert user_count == 1

    finally:
        await engine.dispose()