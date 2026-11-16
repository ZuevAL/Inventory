from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RecoveryEvent(Base):
    __tablename__ = "recovery_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[int] = mapped_column(Integer, index=True)
    outcome: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(128))

    __table_args__ = (
        Index("ix_recovery_events_user_time", "user_id", "occurred_at"),
        Index("ix_recovery_events_source_time", "source", "occurred_at"),
    )


class RecoveryLimit(Base):
    __tablename__ = "recovery_limits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, index=True)
    attempts: Mapped[int] = mapped_column(Integer)
