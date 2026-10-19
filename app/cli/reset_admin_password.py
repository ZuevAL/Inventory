import argparse
import asyncio
from time import time

from sqlalchemy import select, text, update

from app.core.security import generate_temporary_password, hash_password
from app.db import AsyncSessionLocal, engine
from app.models.auth_session import AuthSession
from app.models.user import User


async def reset_admin_password(login: str) -> str:
    temporary_password = generate_temporary_password()
    password_hash = hash_password(temporary_password)

    try:
        async with AsyncSessionLocal() as db:
            try:
                # Сериализуем изменение, как и другие операции с авторизацией.
                await db.execute(text("BEGIN IMMEDIATE"))

                user = await db.scalar(
                    select(User).where(User.login == login.lower())
                )

                if user is None or user.role != "admin":
                    raise ValueError("Администратор с таким логином не найден")

                user.password_hash = password_hash
                user.must_change_password = True
                user.credential_version += 1

                await db.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.user_id == user.id,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=int(time()))
                )

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