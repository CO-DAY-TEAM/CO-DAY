from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, UniqueConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coday_core.db.base import Base, CreatedAt, UpdatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from coday_core.db.models.user import User
    from coday_core.db.models.review_issue import ReviewIssue

class IssueFeedback(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "issue_feedback"

    # 제약 조건 및 인덱스 설정
    __table_args__ = (
        UniqueConstraint("issue_id", "user_id"),
        CheckConstraint("feedback_type IN ('helpful', 'not_helpful')", name="feedback_type_allowed"),
        Index("ix_issue_feedback_user_created", "user_id", text("created_at DESC")),
    )

    issue_id: Mapped[UUID] = mapped_column(ForeignKey("review_issues.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 관계 설정
    user: Mapped["User"] = relationship(back_populates="feedback", lazy="raise")
    issue: Mapped["ReviewIssue"] = relationship(back_populates="feedback", lazy="raise")
