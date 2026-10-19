from fastapi import APIRouter
from app.routers.products import router as products_router
from app.routers.shelves import router as shelves_router
from app.routers.shelf_stock import router as shelf_stock_router
from app.routers.health_check import router as health_check
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router


api_router = APIRouter()
api_router.include_router(products_router)
api_router.include_router(shelves_router)
api_router.include_router(shelf_stock_router)
api_router.include_router(health_check)
api_router.include_router(auth_router)
api_router.include_router(users_router)
