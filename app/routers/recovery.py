from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import clear_auth_cookies, require_csrf
from app.db import get_db
from app.dependencies import get_current_session
from app.schemas.recovery import (
    RecoveryActivateRequest,
    RecoveryIssueRequest,
    RecoveryRequest,
)
from app.services import recovery
from app.services.auth import AuthContext

router = APIRouter(prefix="/auth", tags=["Восстановление доступа"])
CurrentSession = Annotated[AuthContext, Depends(get_current_session)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/recovery/code")
async def issue_code(
    data: RecoveryIssueRequest,
    context: CurrentSession,
    db: DatabaseSession,
):
    return await recovery.issue_code(
        context, data.current_password.get_secret_value(), db
    )


@router.post("/recovery/activate")
async def activate_code(
    data: RecoveryActivateRequest,
    context: CurrentSession,
    db: DatabaseSession,
):
    await recovery.activate_code(context, data.recovery_code.get_secret_value(), db)
    return {"message": "Код восстановления активирован"}


@router.post("/web/password/recover", dependencies=[Depends(require_csrf)])
async def recover_password(
    data: RecoveryRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
):
    source = request.client.host[:128] if request.client else "unknown"
    await recovery.recover_password(data, source, db)
    clear_auth_cookies(response)
    return {"message": "Пароль изменён. Войдите с новым паролем"}


@router.get("/recovery/history")
async def history(
    context: CurrentSession,
    db: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    return await recovery.history(context, db, offset, limit)
