import hashlib
import re
import secrets

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core import tokens
from app.core.errors import AuthError
from app.core.security import hash_password
from app.models.recovery import RecoveryEvent, RecoveryLimit
from app.models.user import User
from app.schemas.recovery import RecoveryRequest
from app.services.auth import (
    AuthContext,
    _replace_password,
    _require_session,
    auth_transaction,
    check_password,
)

CODE_CONFIRM_SECONDS = 15 * 60
RATE_WINDOW_SECONDS = 15 * 60
HISTORY_SECONDS = 90 * 86400


def code_hash(code: str) -> str:
    normalized = code.replace("-", "").replace(" ", "").upper()
    if not re.fullmatch(r"[0-9A-F]{32}", normalized):
        normalized = "invalid"
    return hashlib.sha256(("inventory-recovery:" + normalized).encode()).hexdigest()


def clear_pending_code(user: User) -> None:
    user.pending_recovery_hash = None
    user.pending_recovery_session_id = None
    user.pending_recovery_expires_at = None


async def recovery_admin(db: AsyncSession, context: AuthContext) -> User:
    user, _ = await _require_session(
        db,
        context.user.id,
        context.session_id,
        context.credential_version,
    )
    if user.role != "admin":
        raise AuthError("forbidden", "Действие доступно только администратору", 403)
    return user


async def issue_code(context: AuthContext, password: str, db: AsyncSession) -> dict:
    error = None
    async with auth_transaction(db):
        user = await recovery_admin(db, context)
        retry_after = await take_attempt(
            db,
            "issue:" + str(user.id),
            "session:" + context.session_id,
            tokens.utc_timestamp(),
        )
        if retry_after:
            error = AuthError(
                "recovery_limited",
                "Слишком много попыток. Повторите позже",
                429,
                retry_after=retry_after,
            )
        elif not await check_password(password, user.password_hash):
            error = AuthError(
                "invalid_current_password", "Неверный текущий пароль", 400
            )
        else:
            raw = secrets.token_hex(16).upper()
            code = "-".join(raw[index : index + 4] for index in range(0, len(raw), 4))
            user.pending_recovery_hash = code_hash(code)
            user.pending_recovery_session_id = context.session_id
            user.pending_recovery_expires_at = (
                tokens.utc_timestamp() + CODE_CONFIRM_SECONDS
            )
    if error is not None:
        raise error
    return {"recovery_code": code, "expires_in": CODE_CONFIRM_SECONDS}


async def activate_code(context: AuthContext, code: str, db: AsyncSession) -> None:
    async with auth_transaction(db):
        user = await recovery_admin(db, context)
        if (
            user.pending_recovery_hash is None
            or user.pending_recovery_session_id != context.session_id
            or (user.pending_recovery_expires_at or 0) <= tokens.utc_timestamp()
            or not secrets.compare_digest(user.pending_recovery_hash, code_hash(code))
        ):
            raise AuthError(
                "recovery_confirmation_stale",
                "Выпустите новый код и сохраните его",
                409,
            )
        user.recovery_code_hash = user.pending_recovery_hash
        clear_pending_code(user)


async def take_attempt(db: AsyncSession, login: str, source: str, now: int) -> int:
    """Persistent fixed windows shared by processes; rejected requests don't extend them."""
    await db.execute(
        delete(RecoveryLimit).where(
            RecoveryLimit.window_start <= now - RATE_WINDOW_SECONDS,
        )
    )
    limits = []
    for value, maximum in (
        ("source:" + source, 30),
        ("account-source:" + login + ":" + source, 5),
    ):
        key = hashlib.sha256(value.encode()).hexdigest()
        bucket = await db.get(RecoveryLimit, key)
        if bucket is None:
            bucket = RecoveryLimit(key=key, window_start=now, attempts=0)
        limits.append((bucket, maximum))
    blocked = [
        bucket.window_start + RATE_WINDOW_SECONDS - now
        for bucket, maximum in limits
        if bucket.attempts >= maximum
    ]
    if blocked:
        return max(blocked)
    for bucket, _ in limits:
        db.add(bucket)
        bucket.attempts += 1
    return 0


async def prune_history(db: AsyncSession, now: int) -> None:
    await db.execute(
        delete(RecoveryEvent).where(RecoveryEvent.occurred_at < now - HISTORY_SECONDS)
    )


async def history(
    context: AuthContext, db: AsyncSession, offset: int, limit: int
) -> list[dict]:
    async with auth_transaction(db):
        user = await recovery_admin(db, context)
        await prune_history(db, tokens.utc_timestamp())
        events = (
            await db.scalars(
                select(RecoveryEvent)
                .where(
                    RecoveryEvent.user_id == user.id,
                )
                .order_by(RecoveryEvent.occurred_at.desc(), RecoveryEvent.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        result = [
            {
                "id": event.id,
                "occurred_at": event.occurred_at,
                "outcome": event.outcome,
                "source": event.source,
            }
            for event in events
        ]
    return result


async def recover_password(
    data: RecoveryRequest, source: str, db: AsyncSession
) -> None:
    error = None
    async with auth_transaction(db):
        now = tokens.utc_timestamp()
        await prune_history(db, now)
        retry_after = await take_attempt(db, data.login, source, now)
        user = await db.scalar(select(User).where(User.login == data.login))
        expected = user.recovery_code_hash if user is not None else None
        valid = secrets.compare_digest(
            expected or "0" * 64, code_hash(data.recovery_code.get_secret_value())
        )
        if retry_after:
            error = AuthError(
                "recovery_limited",
                "Слишком много попыток. Повторите позже",
                429,
                retry_after=retry_after,
            )
        elif (
            user is None
            or user.role != "admin"
            or user.must_change_password
            or not expected
            or not valid
        ):
            error = AuthError(
                "invalid_recovery", "Неверный логин или код восстановления", 400
            )
        else:
            password = data.new_password.get_secret_value()
            if await check_password(password, user.password_hash):
                error = AuthError(
                    "password_unchanged",
                    "Новый пароль должен отличаться от текущего",
                    400,
                )
            else:
                new_hash = await run_in_threadpool(hash_password, password)
                await _replace_password(db, user, new_hash, False)
                user.recovery_code_hash = None
                clear_pending_code(user)
        event_user_id = user.id if user is not None and user.role == "admin" else None
        suppressed = None
        if retry_after:
            # One marker per target/source/window, including unknown targets.
            # A stream of rejected requests must not grow the audit table forever.
            suppressed = await db.scalar(
                select(RecoveryEvent.id)
                .where(
                    RecoveryEvent.user_id == event_user_id,
                    RecoveryEvent.source == source,
                    RecoveryEvent.outcome == "rate_limited",
                    RecoveryEvent.occurred_at
                    >= now + retry_after - RATE_WINDOW_SECONDS,
                )
                .limit(1)
            )
        if suppressed is None:
            db.add(
                RecoveryEvent(
                    user_id=event_user_id,
                    occurred_at=now,
                    source=source,
                    outcome="rate_limited"
                    if retry_after
                    else "failure"
                    if error
                    else "success",
                )
            )
    # Failed attempts and their rate limits must commit too.
    if error is not None:
        raise error
