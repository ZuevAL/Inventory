from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import (
    ACCESS_COOKIE, PENDING_COOKIE, REFRESH_COOKIE, browser_context,
    clear_auth_cookies, clear_pending, require_csrf, set_auth_cookies,
    set_csrf_cookie, set_pending_cookie,
)
from app.core.errors import AuthError
from app.db import get_db
from app.dependencies import get_current_auth
from app.schemas.auth import (
    AuthResult, BrowserAuthResult, BrowserLoginConfirmRequest,
    LoginConfirmRequest, LoginConfirmationRequired, LoginRequest,
    PasswordChangeRequest, PasswordSetRequest, PasswordSetupRequest,
    RefreshRequest, TokenPair,
)
from app.schemas.users import UserRead
from app.services import auth as service
from app.services.auth import AuthContext

router = APIRouter(prefix="/auth", tags=["Авторизация"])


@router.post("/login", response_model=AuthResult)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await service.login(data, db)


@router.post("/confirm-login", response_model=TokenPair)
async def confirm_login(data: LoginConfirmRequest, db: AsyncSession = Depends(get_db)):
    return await service.confirm_login(data.confirmation_token.get_secret_value(), db)


@router.post("/password/setup", response_model=TokenPair)
async def setup_password(data: PasswordSetupRequest, db: AsyncSession = Depends(get_db)):
    return await service.setup_password(
        data.password_setup_token.get_secret_value(), data.new_password.get_secret_value(), db,
    )


@router.post("/password/change")
async def change_password(
    data: PasswordChangeRequest, response: Response,
    context: AuthContext = Depends(get_current_auth), db: AsyncSession = Depends(get_db),
):
    await service.change_password(
        context, data.current_password.get_secret_value(), data.new_password.get_secret_value(), db,
    )
    clear_auth_cookies(response)
    return {"message": "Пароль изменён. Войдите снова"}


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await service.refresh(data.refresh_token.get_secret_value(), db)


@router.post("/logout", status_code=204)
async def logout(
    request: Request, context: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
):
    authorization = request.headers.get("authorization")
    token = authorization.split(" ", 1)[1] if authorization else request.cookies[ACCESS_COOKIE]
    await service.logout(token, db)
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserRead)
async def me(context: AuthContext = Depends(get_current_auth)):
    return context.user


def browser_result(request: Request, response: Response, result) -> BrowserAuthResult:
    if isinstance(result, TokenPair):
        set_auth_cookies(request, response, result)
        return BrowserAuthResult(
            status=result.status, user=result.user, expires_in=result.expires_in,
            session_expires_at=result.session_expires_at,
        )
    if isinstance(result, LoginConfirmationRequired):
        token = result.confirmation_token
    else:
        token = result.password_setup_token
    set_pending_cookie(request, response, token, result.expires_in)
    return BrowserAuthResult(
        status=result.status, expires_in=result.expires_in, message=result.message,
    )


@router.get("/web/csrf")
async def csrf(request: Request, response: Response):
    return {"csrf_token": set_csrf_cookie(request, response, browser_context(request))}


@router.post("/web/login", response_model=BrowserAuthResult, dependencies=[Depends(require_csrf)])
async def web_login(
    data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db),
):
    return browser_result(request, response, await service.login(data, db))


@router.post("/web/confirm-login", response_model=BrowserAuthResult, dependencies=[Depends(require_csrf)])
async def web_confirm_login(
    data: BrowserLoginConfirmRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(PENDING_COOKIE)
    if not token:
        raise AuthError("confirmation_stale", "Повторите вход")
    return browser_result(request, response, await service.confirm_login(token, db))


@router.post("/web/password/setup", response_model=BrowserAuthResult, dependencies=[Depends(require_csrf)])
async def web_setup_password(
    data: PasswordSetRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(PENDING_COOKIE)
    if not token:
        raise AuthError("setup_stale", "Повторите вход с временным паролем")
    return browser_result(request, response, await service.setup_password(
        token, data.new_password.get_secret_value(), db,
    ))


@router.post("/web/refresh", response_model=BrowserAuthResult, dependencies=[Depends(require_csrf)])
async def web_refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    try:
        if not token:
            raise AuthError("authentication_required", "Войдите в приложение")
        result = await service.refresh(token, db)
    except AuthError as exc:
        error_response = JSONResponse(
            {"detail": exc.message, "code": exc.code}, status_code=exc.status_code,
        )
        clear_auth_cookies(error_response)
        return error_response
    return browser_result(request, response, result)


@router.post("/web/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def web_logout(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE) or request.cookies.get(ACCESS_COOKIE)
    if token:
        try:
            await service.logout(token, db)
        except AuthError:
            pass  # Logout remains idempotent for an expired/missing session.
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response


@router.post("/web/cancel-login", dependencies=[Depends(require_csrf)])
async def cancel_login(request: Request, response: Response):
    clear_pending(response)
    set_csrf_cookie(request, response, browser_context(request, include_pending=False))
    return {"message": "Вход отменён. Предыдущая сессия не изменена"}
