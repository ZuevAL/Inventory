import argparse
import asyncio

from sqlalchemy import select

from app.core.security import generate_temporary_password, hash_password
from app.db import AsyncSessionLocal, begin_auth_write, engine
from app.models.user import User
from app.services.auth import _replace_password


async def reset_admin_password(login: str) -> str:
    temporary_password = generate_temporary_password()
    password_hash = hash_password(temporary_password)

    try:
        async with AsyncSessionLocal() as db:
            try:
                # Сериализуем изменение, как и другие операции с авторизацией.
                await begin_auth_write(db)

                user = await db.scalar(
                    select(User).where(User.login == login.lower())
                )

                if user is None or user.role != "admin":
                    raise ValueError("Администратор с таким логином не найден")

                await _replace_password(db, user, password_hash, True)

                await db.commit()
                return temporary_password

            except BaseException:
                await db.rollback()
                raise
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Сброс временного пароля администратора"
    )
    parser.add_argument("--login", required=True)
    args = parser.parse_args()

    try:
        temporary_password = asyncio.run(
            reset_admin_password(args.login)
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(f"Новый временный пароль: {temporary_password}")
    print("Сохраните его: повторно показать пароль будет невозможно.")


if __name__ == "__main__":
    main()
