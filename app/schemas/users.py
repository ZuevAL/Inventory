from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

class LoginBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )

    @field_validator("login")
    @classmethod
    def normalize_login(cls, value: str) -> str:
        return value.lower()


class UserCreate(LoginBase):
    full_name: str = Field(
        min_length=1,
        max_length=255,
    )

    role: Literal["admin", "worker"] = "worker"

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("ФИО не должно быть пустым")

        return value

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    full_name: str
    role: Literal["admin", "worker"]
    must_change_password: bool


class UserCreateResponse(BaseModel):
    user: UserRead
    temporary_password: str