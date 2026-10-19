import asyncio
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import hash_password
from app.db import get_db
from app.main import create_app
from app.models.base import Base
from app.models.user import User

TEST_PASSWORD = "Correct test password 123"


@dataclass
class AuthEnvironment:
    client: TestClient
    application: object
    session_factory: object

    def create_user(self, login="worker_01", role="worker", temporary=False, password=TEST_PASSWORD):
        async def create():
            async with self.session_factory() as db:
                user = User(
                    login=login, full_name="Тестовый пользователь", role=role,
                    password_hash=hash_password(password), must_change_password=temporary,
                )
                db.add(user)
                await db.commit()
                return user.id
        return asyncio.run(create())

    def database(self, operation):
        async def run():
            async with self.session_factory() as db:
                result = await operation(db)
                await db.commit()
                return result
        return asyncio.run(run())


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", SecretStr("unit-test-key-" + "0" * 64))
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + (tmp_path / "auth.db").as_posix(), poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(initialize())
    application = create_app()

    async def test_db():
        async with session_factory() as db:
            yield db

    application.dependency_overrides[get_db] = test_db
    try:
        with TestClient(application) as client:
            yield AuthEnvironment(client, application, session_factory)
    finally:
        application.dependency_overrides.clear()
        asyncio.run(engine.dispose())
