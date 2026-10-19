from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from app.schemas.users import LoginBase, UserRead

class PasswordSetRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
    )

    new_password: SecretStr = Field(
        min_length=15,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        password = value.get_secret_value()

        if not password.isprintable():
            raise ValueError(
                "Пароль не должен содержать "
                "управляющие или непечатные символы"
            )

        return value


class PasswordChangeRequest(PasswordSetRequest):
    current_password: SecretStr = Field(
        min_length=1,
        max_length=128,
    )

class LoginRequest(LoginBase):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
    )

    password: SecretStr = Field(
        min_length=1,
        max_length=128,
    )


class SecretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class LoginConfirmRequest(SecretRequest):
    confirmation_token: SecretStr = Field(min_length=1, max_length=8192)
    confirm: Literal[True]


class BrowserLoginConfirmRequest(SecretRequest):
    confirm: Literal[True]


class PasswordSetupRequest(PasswordSetRequest):
    password_setup_token: SecretStr = Field(min_length=1, max_length=8192)


class RefreshRequest(SecretRequest):
    refresh_token: SecretStr = Field(min_length=1, max_length=8192)


class TokenPair(BaseModel):
    status: Literal["authenticated"] = "authenticated"
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    session_expires_at: int
    user: UserRead


class LoginConfirmationRequired(BaseModel):
    status: Literal["confirm_login"] = "confirm_login"
    confirmation_token: str
    expires_in: int
    message: str = "Вы уже вошли. Продолжить вход и завершить предыдущую сессию?"


class PasswordSetupRequired(BaseModel):
    status: Literal["password_setup"] = "password_setup"
    password_setup_token: str
    expires_in: int
    message: str = "Установите постоянный пароль"


AuthResult = Annotated[
    TokenPair | LoginConfirmationRequired | PasswordSetupRequired,
    Field(discriminator="status"),
]


class BrowserAuthResult(BaseModel):
    status: Literal["authenticated", "confirm_login", "password_setup"]
    user: UserRead | None = None
    expires_in: int
    session_expires_at: int | None = None
    message: str | None = None
