from functools import lru_cache
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Inventory API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./sql_app.db"

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "inventory-api"
    jwt_audience: str = "inventory-client"
    access_token_expire_minutes: int = Field(default=15, gt=0)
    session_expire_hours: int = Field(default=12, gt=0)
    login_confirm_expire_minutes: int = Field(default=5, gt=0)
    password_setup_expire_minutes: int = Field(default=5, gt=0)
    auth_cookie_secure: bool = False  # True при работе через HTTPS.

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

