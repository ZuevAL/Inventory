from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        return {"message": settings.app_name}

    return application


app = create_app()

