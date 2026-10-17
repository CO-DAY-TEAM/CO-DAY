from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Identity, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coday_core.db.base import Base, CreatedAt
if TYPE_CHECKING:
    from coday_core.db.models.review import Review

class ReviewEvent(CreatedAt, Base):
    __tablename__ = "review_events"

    # 제약 조건 및 인덱스 설정
    __table_args__ = (
        CheckConstraint("level IN ('info', 'warning', 'error')", name="level_allowed"),
        Index("ix_review_events_review_id_id", "review_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("reviews.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'info'"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)

    # 관계 설정
    review: Mapped["Review"] = relationship(back_populates="events", lazy="raise")