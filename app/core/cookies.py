import hashlib
import hmac
import secrets

from fastapi import Request, Response

from app.core.config import settings
from app.core.errors import AuthError
from app.core.tokens import decode_token, utc_timestamp
from app.schemas.auth import TokenPair

ACCESS_COOKIE = "inventory_access"
REFRESH_COOKIE = "inventory_refresh"
PENDING_COOKIE = "inventory_pending"
CSRF_COOKIE = "inventory_csrf"


def auth_cookie_path() -> str:
    return settings.api_v1_prefix + "/auth"


def browser_context(request: Request, include_pending: bool = True) -> str:
    if include_pending and request.cookies.get(PENDING_COOKIE):
        try:
            return decode_token(
                request.cookies[PENDING_COOKIE], ("login_confirm", "password_setup"),
            ).jti
        except AuthError:
            pass
    if request.cookies.get(REFRESH_COOKIE):
        try:
            return decode_token(request.cookies[REFRESH_COOKIE], "refresh").sid
        except AuthError:
            pass
    # Refresh is intentionally scoped to /auth and is absent on warehouse routes.
    if request.cookies.get(ACCESS_COOKIE):
        try:
            return decode_token(request.cookies[ACCESS_COOKIE], "access").sid
        except AuthError:
            pass
    return "anonymous"


def _csrf_signature(context: str, nonce: str) -> str:
    return hmac.new(
        settings.jwt_secret_key.get_secret_value().encode(),
        f"csrf:{context}:{nonce}".encode(), hashlib.sha256,
    ).hexdigest()


def _valid_csrf(token: str, context: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != context or len(parts[1]) != 64:
        return False
    expected = _csrf_signature(context, parts[1])
    return secrets.compare_digest(parts[2].encode(), expected.encode())


def set_csrf_cookie(request: Request, response: Response, context: str) -> str:
    existing = request.cookies.get(CSRF_COOKIE, "")
    if _valid_csrf(existing, context):
        return existing  # Keep it stable during refresh and across browser tabs.
    nonce = secrets.token_hex(32)
    token = f"{context}.{nonce}.{_csrf_signature(context, nonce)}"
    response.set_cookie(
        CSRF_COOKIE, token, max_age=settings.session_expire_hours * 3600,
        path="/", secure=settings.auth_cookie_secure, httponly=False, samesite="strict",
    )
    return token


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if (
        not cookie or len(cookie) > 512 or len(header) > 512
        or not secrets.compare_digest(cookie.encode(), header.encode())
        or not _valid_csrf(cookie, browser_context(request))
    ):
        raise AuthError("csrf_invalid", "Обновите страницу и повторите действие", 403)


def _set_http_only(response: Response, name: str, value: str, ttl: int, path: str):
    response.set_cookie(
        name, value, max_age=max(0, ttl), path=path,
        secure=settings.auth_cookie_secure, httponly=True, samesite="strict",
    )


def clear_pending(response: Response) -> None:
    response.delete_cookie(
        PENDING_COOKIE, path=auth_cookie_path(), secure=settings.auth_cookie_secure,
        httponly=True, samesite="strict",
    )


def clear_auth_cookies(response: Response) -> None:
    for name, path, http_only in (
        (ACCESS_COOKIE, settings.api_v1_prefix, True),
        (REFRESH_COOKIE, auth_cookie_path(), True),
        (PENDING_COOKIE, auth_cookie_path(), True),
        (CSRF_COOKIE, "/", False),
    ):
        response.delete_cookie(
            name, path=path, secure=settings.auth_cookie_secure,
            httponly=http_only, samesite="strict",
        )


def set_auth_cookies(request: Request, response: Response, pair: TokenPair) -> None:
    access = decode_token(pair.access_token, "access")
    _set_http_only(
        response, ACCESS_COOKIE, pair.access_token,
        access.exp - utc_timestamp(), settings.api_v1_prefix,
    )
    _set_http_only(
        response, REFRESH_COOKIE, pair.refresh_token,
        pair.session_expires_at - utc_timestamp(), auth_cookie_path(),
    )
    clear_pending(response)
    set_csrf_cookie(request, response, access.sid)


def set_pending_cookie(request: Request, response: Response, token: str, ttl: int) -> None:
    claims = decode_token(token, ("login_confirm", "password_setup"))
    if claims.token_type == "password_setup":
        clear_auth_cookies(response)
    _set_http_only(response, PENDING_COOKIE, token, ttl, auth_cookie_path())
    set_csrf_cookie(request, response, claims.jti)
