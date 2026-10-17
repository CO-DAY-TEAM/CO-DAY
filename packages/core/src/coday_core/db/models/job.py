from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship  

from coday_core.db.base import (
    Base,
    CreatedAt,
    UpdatedAt,
    UUIDPrimaryKey,
)

if TYPE_CHECKING:
    from coday_core.db.models.review import Review

class Job(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "jobs"

    # 제약 조건 및 인덱스 설정 
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint("attempts <= max_attempts", name="attempts_limit"),
        Index("ix_jobs_queued", "available_at", "created_at", postgresql_where=text("status = 'queued'")),
        Index("ix_jobs_expired", "locked_until", postgresql_where=text("status = 'running'")),
    )

    review_id: Mapped[UUID] = mapped_column(ForeignKey("reviews.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 관계 설정 
    review: Mapped["Review"] = relationship(back_populates="job", lazy="raise")