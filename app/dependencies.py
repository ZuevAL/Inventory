from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import ACCESS_COOKIE, require_csrf
from app.core.errors import AuthError
from app.db import get_db
from app.services.auth import AuthContext, authenticate_access

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if credentials is not None:
        token = credentials.credentials
    elif request.headers.get("authorization"):
        raise AuthError("invalid_token", "Используйте заголовок Authorization: Bearer")
    else:
        token = request.cookies.get(ACCESS_COOKIE)
        if token is None:
            raise AuthError("authentication_required", "Войдите в приложение")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_csrf(request)
    return await authenticate_access(token, db)


async def require_admin(context: AuthContext = Depends(get_current_auth)) -> AuthContext:
    if context.user.role != "admin":
        raise AuthError("forbidden", "Действие доступно только администратору", 403)
    return context
