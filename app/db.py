from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from app.core.config import settings



SQLALCHEMY_DATABASE_URL = settings.database_url


@event.listens_for(Engine, "engine_connect")
def configure_sqlite_connection(connection: Connection):
    if connection.dialect.name != "sqlite" or connection.info.get("sqlite_configured"):
        return
    cursor = connection.connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
    finally:
        cursor.close()
    connection.info["sqlite_configured"] = True


engine = create_async_engine(SQLALCHEMY_DATABASE_URL)


AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)




async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


async def begin_auth_write(db: AsyncSession):
    if db.get_bind().dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))
    else:
        # Transaction-scoped lock for session rotation and first-admin creation.
        await db.execute(text("SELECT pg_advisory_xact_lock(2370741041)"))

