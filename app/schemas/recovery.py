from typing import Literal

from pydantic import Field, SecretStr, model_validator

from app.schemas.auth import PasswordSetRequest, SecretRequest
from app.schemas.users import LoginBase


class RecoveryIssueRequest(SecretRequest):
    current_password: SecretStr = Field(min_length=1, max_length=128)


class RecoveryActivateRequest(SecretRequest):
    recovery_code: SecretStr = Field(min_length=1, max_length=128)
    saved: Literal[True]


class RecoveryRequest(PasswordSetRequest, LoginBase):
    recovery_code: SecretStr = Field(min_length=1, max_length=128)
    repeat_password: SecretStr = Field(min_length=15, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if (
            self.new_password.get_secret_value()
            != self.repeat_password.get_secret_value()
        ):
            raise ValueError("Пароли не совпадают")
        return self
