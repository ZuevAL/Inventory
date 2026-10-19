from uuid import uuid4

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.user import User


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id),
        nullable=False,
    )

    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    expires_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    revoked_at: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    current_refresh_jti: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )


Index(
    "uq_sessions_one_open_per_user",
    AuthSession.user_id,
    unique=True,
    sqlite_where=AuthSession.revoked_at.is_(None),
)