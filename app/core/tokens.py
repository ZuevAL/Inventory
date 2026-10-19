from time import time
from typing import Literal
from uuid import UUID, uuid4

import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core.config import settings
from app.core.errors import AuthError

TokenType = Literal["access", "refresh", "login_confirm", "password_setup"]


def utc_timestamp() -> int:
    return int(time())


class TokenClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    iss: str
    aud: str
    sub: str = Field(pattern=r"^[1-9][0-9]*$", max_length=20)
    jti: str
    token_type: TokenType
    iat: int = Field(ge=0)
    exp: int = Field(gt=0)
    credential_version: int = Field(ge=0)
    sid: str | None = None

    @field_validator("jti", "sid")
    @classmethod
    def validate_uuid(cls, value: str | None) -> str | None:
        if value is not None and str(UUID(value)) != value:
            raise ValueError("Invalid UUID")
        return value

    @model_validator(mode="after")
    def validate_context(self):
        if int(self.sub) > 9223372036854775807:
            raise ValueError("Invalid user ID")
        if self.exp <= self.iat:
            raise ValueError("Invalid lifetime")
        if self.token_type == "password_setup":
            if self.sid is not None:
                raise ValueError("Setup token cannot refer to a session")
        elif self.sid is None:
            raise ValueError("Session ID is required")
        return self


def encode_token(
    token_type: TokenType,
    user_id: int,
    credential_version: int,
    expires_at: int,
    session_id: str | None = None,
    jti: str | None = None,
) -> str:
    now = utc_timestamp()
    if expires_at <= now:
        raise AuthError("session_expired", "Время сессии истекло")
    claims = TokenClaims(
        iss=settings.jwt_issuer, aud=settings.jwt_audience,
        sub=str(user_id), sid=session_id, jti=jti or str(uuid4()),
        token_type=token_type, iat=now, exp=expires_at,
        credential_version=credential_version,
    )
    return jwt.encode(
        claims.model_dump(exclude_none=True),
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(
    user_id: int,
    session_id: str,
    session_expires_at: int,
    credential_version: int = 0,
) -> str:
    expires_at = min(
        utc_timestamp() + settings.access_token_expire_minutes * 60,
        session_expires_at,
    )
    return encode_token("access", user_id, credential_version, expires_at, session_id)


def decode_token(token: str, expected_type: TokenType | tuple[TokenType, ...]) -> TokenClaims:
    if len(token) > 8192:
        raise AuthError("invalid_token", "Недействительный токен")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": [
                "iss", "aud", "sub", "jti", "token_type", "iat", "exp", "credential_version",
            ]},
        )
        claims = TokenClaims.model_validate(payload)
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token_expired", "Время действия токена истекло") from exc
    except (jwt.InvalidTokenError, ValidationError, ValueError) as exc:
        raise AuthError("invalid_token", "Недействительный токен") from exc
    allowed = (expected_type,) if isinstance(expected_type, str) else expected_type
    if claims.token_type not in allowed:
        raise AuthError("wrong_token_type", "Этот токен нельзя использовать для данного действия")
    return claims
