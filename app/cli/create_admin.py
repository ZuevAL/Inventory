import argparse
import asyncio

from pydantic import ValidationError

from app.db import AsyncSessionLocal, engine
from app.schemas.users import UserCreate, UserCreateResponse
from app.services.users import (
    UserLoginAlreadyExists,
    FirstAdminAlreadyExists,
    create_first_admin as create_first_admin_service,
)


async def create_first_admin(
    data: UserCreate,
) -> UserCreateResponse:
    try:
        async with AsyncSessionLocal() as db:
            return await create_first_admin_service(data, db)

    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Создание первого администратора",
    )

    parser.add_argument("--login", required=True)
    parser.add_argument("--full-name", required=True)

    args = parser.parse_args()

    try:
        data = UserCreate(
            login=args.login,
            full_name=args.full_name,
            role="admin",
        )

        result = asyncio.run(create_first_admin(data))

    except ValidationError as exc:
        parser.error(str(exc))

    except (
        FirstAdminAlreadyExists,
        UserLoginAlreadyExists,
    ) as exc:
        parser.exit(
            status=1,
            message=f"Ошибка: {exc}\n",
        )

    print("Первый администратор создан.")
    print(f"Логин: {result.user.login}")
    print(f"Временный пароль: {result.temporary_password}")
    print("Сохраните пароль: повторно показать его невозможно.")


if __name__ == "__main__":
    main()
