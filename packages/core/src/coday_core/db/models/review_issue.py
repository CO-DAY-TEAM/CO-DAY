from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coday_core.db.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from coday_core.db.models.review import Review
    from coday_core.db.models.review_file import ReviewFile
    from coday_core.db.models.issue_feedback import IssueFeedback

class ReviewIssue(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "review_issues"

    # 제약 조건 및 인덱스 설정
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_file_id", "review_id"],
            ["review_files.id", "review_files.review_id"],
        ),
        CheckConstraint("end_line > 0", name="end_line_positive"),
        CheckConstraint("start_line IS NULL OR (start_line > 0 AND start_line <= end_line)", name="line_range"),
        CheckConstraint("line_side IN ('LEFT', 'RIGHT')", name="line_side_allowed"),
        Index("ix_review_issues_review_type", "review_id", "issue_type"),
        Index("ix_review_issues_file_line", "review_file_id", "end_line"),
        Index("ix_review_issues_fingerprint", "fingerprint"),
    )

    review_id: Mapped[UUID] = mapped_column(ForeignKey("reviews.id"), nullable=False)
    review_file_id: Mapped[UUID] = mapped_column(ForeignKey("review_files.id"), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    line_side: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'RIGHT'"))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    post_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    github_comment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 관계 설정
    review: Mapped["Review"] = relationship(back_populates="issues", foreign_keys=[review_id], lazy="raise")
    review_file: Mapped["ReviewFile"] = relationship(back_populates="issues", foreign_keys=[review_file_id], lazy="raise")
    feedback: Mapped[list["IssueFeedback"]] = relationship(back_populates="issue", lazy="raise", passive_deletes="all")