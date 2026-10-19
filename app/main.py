from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path

from app.routers.api_router import api_router
from app.core.config import settings
from app.core.errors import AuthError
from app.db import engine


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.exception_handler(AuthError)
    async def auth_error_handler(request, exc: AuthError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else {}
        return JSONResponse(
            {"detail": exc.message, "code": exc.code},
            status_code=exc.status_code, headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc: RequestValidationError):
        # Never echo passwords, JWTs or full rejected request bodies into HTTP errors.
        errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                  for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @application.middleware("http")
    async def prevent_auth_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(settings.api_v1_prefix + "/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


    @application.get("/", tags=["Root"])
    async def root():
        return {"message": settings.app_name}

    application.mount("/static", StaticFiles(
        directory=str(Path(__file__).resolve().parent / "static"), html=True,
    ))
    return application


app = create_app()
