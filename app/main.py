from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.routers.api_router import api_router
from app.core.config import settings
from app.db import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    print("Tables created")
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)


    @application.get("/", tags=["Root"])
    async def root():
        return {"message": settings.app_name}

    return application


app = create_app()
