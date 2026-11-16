from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from sqlalchemy import Boolean, CheckConstraint, Integer, String, true

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    login: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="worker",
        server_default="worker",
    )

    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    credential_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    recovery_code_hash: Mapped[str | None] = mapped_column(String(64))
    pending_recovery_hash: Mapped[str | None] = mapped_column(String(64))
    pending_recovery_session_id: Mapped[str | None] = mapped_column(String(36))
    pending_recovery_expires_at: Mapped[int | None] = mapped_column(Integer)

    @property
    def recovery_required(self) -> bool:
        return self.role == "admin" and self.recovery_code_hash is None

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'worker')",
            name="ck_users_role",
        ),
    )
