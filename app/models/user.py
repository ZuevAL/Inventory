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

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'worker')",
            name="ck_users_role",
        ),
    )
