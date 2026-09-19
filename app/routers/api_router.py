from fastapi import APIRouter
from app.routers.products import router as products_router
from app.routers.health_check import router as health_check
api_router = APIRouter()
api_router.include_router(products_router)
api_router.include_router(health_check)