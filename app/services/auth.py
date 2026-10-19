from contextlib import asynccontextmanager
from dataclasses import dataclass
from secrets import compare_digest
from uuid import uuid4

from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core import tokens
from app.core.config import settings
from app.core.errors import AuthError
from app.core.security import generate_temporary_password, hash_password, verify_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.auth import (
    LoginConfirmationRequired, LoginRequest, PasswordSetupRequired, TokenPair,
)
from app.schemas.users import UserCreateResponse, UserRead

_DUMMY_HASH = hash_password(generate_temporary_password())


@dataclass(frozen=True)
class AuthContext:
    user: UserRead
    session_id: str
    credential_version: int


@asynccontextmanager
async def auth_transaction(db: AsyncSession):
    """Serialize SQLite auth writes; callers must not have pending business changes."""
    if db.in_transaction():
        await db.rollback()  # End the read-only transaction used by auth dependencies.
    try:
        await db.execute(text("BEGIN IMMEDIATE"))
        yield
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def check_password(password: str, password_hash: str) -> bool:
    try:
        return await run_in_threadpool(verify_password, password, password_hash)
    except (UnknownHashError, ValueError):
        return False


async def _active_session(db: AsyncSession, user_id: int) -> AuthSession | None:
    session = await db.scalar(select(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
    ))
    if session is not None and session.expires_at <= tokens.utc_timestamp():
        session.revoked_at = tokens.utc_timestamp()
        await db.flush()
        return None
    return session


async def _require_session(
    db: AsyncSession, user_id: int, session_id: str, credential_version: int,
) -> tuple[User, AuthSession]:
    user = await db.get(User, user_id)
    session = await db.get(AuthSession, session_id)
    now = tokens.utc_timestamp()
    if (
        user is None or session is None or session.user_id != user_id
        or session.revoked_at is not None or session.expires_at <= now
        or user.credential_version != credential_version or user.must_change_password
    ):
        raise AuthError("session_ended", "Сессия завершена. Войдите снова")
    return user, session


async def authenticate_access(token: str, db: AsyncSession) -> AuthContext:
    claims = tokens.decode_token(token, "access")
    user, session = await _require_session(
        db, int(claims.sub), claims.sid, claims.credential_version,
    )
    return AuthContext(UserRead.model_validate(user), session.id, user.credential_version)


def _token_pair(user: User, session: AuthSession) -> TokenPair:
    now = tokens.utc_timestamp()
    access_expires_at = min(
        now + settings.access_token_expire_minutes * 60, session.expires_at,
    )
    return TokenPair(
        access_token=tokens.create_access_token(
            user.id, session.id, session.expires_at, user.credential_version,
        ),
        refresh_token=tokens.encode_token(
            "refresh", user.id, user.credential_version, session.expires_at,
            session.id, session.current_refresh_jti,
        ),
        expires_in=access_expires_at - now,
        session_expires_at=session.expires_at,
        user=UserRead.model_validate(user),
    )


async def _new_session(db: AsyncSession, user: User) -> TokenPair:
    now = tokens.utc_timestamp()
    session = AuthSession(
        id=str(uuid4()), user_id=user.id, created_at=now,
        expires_at=now + settings.session_expire_hours * 60 * 60,
        current_refresh_jti=str(uuid4()),
    )
    db.add(session)
    await db.flush()
    return _token_pair(user, session)


async def login(data: LoginRequest, db: AsyncSession):
    user = await db.scalar(select(User).where(User.login == data.login))
    stored_hash = user.password_hash if user else _DUMMY_HASH
    valid = await check_password(data.password.get_secret_value(), stored_hash)
    if user is None or not valid:
        raise AuthError("invalid_credentials", "Неверный логин или пароль")
    user_id, version = user.id, user.credential_version

    async with auth_transaction(db):
        user = await db.get(User, user_id, populate_existing=True)
        if user is None or user.credential_version != version or not compare_digest(
            user.password_hash, stored_hash,
        ):
            raise AuthError("invalid_credentials", "Неверный логин или пароль")
        if user.must_change_password:
            ttl = settings.password_setup_expire_minutes * 60
            result = PasswordSetupRequired(
                password_setup_token=tokens.encode_token(
                    "password_setup", user.id, version, tokens.utc_timestamp() + ttl,
                ), expires_in=ttl,
            )
        else:
            previous = await _active_session(db, user.id)
            if previous is not None:
                ttl = settings.login_confirm_expire_minutes * 60
                result = LoginConfirmationRequired(
                    confirmation_token=tokens.encode_token(
                        "login_confirm", user.id, version, tokens.utc_timestamp() + ttl,
                        previous.id,
                    ), expires_in=ttl,
                )
            else:
                result = await _new_session(db, user)
    return result


async def confirm_login(token: str, db: AsyncSession) -> TokenPair:
    claims = tokens.decode_token(token, "login_confirm")
    async with auth_transaction(db):
        user = await db.get(User, int(claims.sub))
        previous = await db.get(AuthSession, claims.sid)
        if (
            user is None or user.must_change_password
            or user.credential_version != claims.credential_version
            or previous is None or previous.user_id != user.id
            or previous.revoked_at is not None
        ):
            raise AuthError(
                "confirmation_stale", "Подтверждение устарело. Повторите вход", 409,
            )
        previous.revoked_at = tokens.utc_timestamp()
        await db.flush()  # Release the one-open-session unique index before INSERT.
        result = await _new_session(db, user)
    return result


async def _replace_password(
    db: AsyncSession, user: User, password_hash: str, must_change: bool,
) -> None:
    """Shared password installation for first setup, change and admin reset."""
    user.password_hash = password_hash
    user.must_change_password = must_change
    user.credential_version += 1
    await db.execute(update(AuthSession).where(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None),
    ).values(revoked_at=tokens.utc_timestamp()))
    await db.flush()


async def setup_password(token: str, new_password: str, db: AsyncSession) -> TokenPair:
    claims = tokens.decode_token(token, "password_setup")
    new_hash = await run_in_threadpool(hash_password, new_password)
    async with auth_transaction(db):
        user = await db.get(User, int(claims.sub))
        if user is None or not user.must_change_password or (
            user.credential_version != claims.credential_version
        ):
            raise AuthError("setup_stale", "Повторите вход с временным паролем")
        if await check_password(new_password, user.password_hash):
            raise AuthError("password_unchanged", "Выберите пароль, отличный от временного", 400)
        await _replace_password(db, user, new_hash, False)
        result = await _new_session(db, user)
    return result


async def change_password(
    context: AuthContext, current_password: str, new_password: str, db: AsyncSession,
) -> None:
    user = await db.get(User, context.user.id)
    if user is None or not await check_password(current_password, user.password_hash):
        raise AuthError("invalid_current_password", "Неверный текущий пароль", 400)
    if new_password == current_password:
        raise AuthError("password_unchanged", "Новый пароль должен отличаться от текущего", 400)
    new_hash = await run_in_threadpool(hash_password, new_password)
    async with auth_transaction(db):
        user, _ = await _require_session(
            db, context.user.id, context.session_id, context.credential_version,
        )
        await _replace_password(db, user, new_hash, False)


async def refresh(token: str, db: AsyncSession) -> TokenPair:
    claims = tokens.decode_token(token, "refresh")
    reused = False
    async with auth_transaction(db):
        user, session = await _require_session(
            db, int(claims.sub), claims.sid, claims.credential_version,
        )
        if not compare_digest(session.current_refresh_jti, claims.jti):
            session.revoked_at = tokens.utc_timestamp()
            reused = True
        else:
            session.current_refresh_jti = str(uuid4())
            result = _token_pair(user, session)
    # Raise only after committing revocation; raising inside the transaction rolls it back.
    if reused:
        raise AuthError("refresh_reused", "Refresh-токен уже использован. Войдите снова")
    return result


async def logout(token: str, db: AsyncSession) -> None:
    claims = tokens.decode_token(token, ("access", "refresh"))
    async with auth_transaction(db):
        session = await db.get(AuthSession, claims.sid)
        if session is not None and session.user_id == int(claims.sub) and session.revoked_at is None:
            session.revoked_at = tokens.utc_timestamp()


async def reset_password(
    context: AuthContext, user_id: int, db: AsyncSession,
) -> UserCreateResponse:
    temporary_password = generate_temporary_password()
    new_hash = await run_in_threadpool(hash_password, temporary_password)
    async with auth_transaction(db):
        actor, _ = await _require_session(
            db, context.user.id, context.session_id, context.credential_version,
        )
        if actor.role != "admin":
            raise AuthError("forbidden", "Действие доступно только администратору", 403)
        target = await db.get(User, user_id)
        if target is None:
            raise AuthError("user_not_found", "Пользователь не найден", 404)
        await _replace_password(db, target, new_hash, True)
        result = UserCreateResponse(
            user=UserRead.model_validate(target), temporary_password=temporary_password,
        )
    return result
