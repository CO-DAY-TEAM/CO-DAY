from __future__ import annotations

from datetime import datetime
from uuid import UUID
from typing import TYPE_CHECKING

from coday_core.db.models.review_file import ReviewFile
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coday_core.db.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from coday_core.db.models.repository import Repository
    from coday_core.db.models.job import Job
    from coday_core.db.models.review_issue import ReviewIssue
    from coday_core.db.models.review_event import ReviewEvent

class Review(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "reviews"

    # 제약 조건 및 인덱스 설정 
    __table_args__ = (
        CheckConstraint("pr_number > 0", name="pr_number_positive"),
        CheckConstraint("files_changed >= 0", name="files_changed_nonnegative"),
        CheckConstraint("additions >= 0", name="additions_nonnegative"),
        CheckConstraint("deletions >= 0", name="deletions_nonnegative"),
        CheckConstraint("chunk_total >= 0", name="chunk_total_nonnegative"),
        CheckConstraint("chunk_done >= 0", name="chunk_done_nonnegative"),
        CheckConstraint("chunk_done <= chunk_total", name="chunk_progress"),
        CheckConstraint("duration_ms >= 0", name="duration_nonnegative"),
        CheckConstraint("retry_of IS NULL OR retry_of <> id", name="retry_not_self"),
        Index("ix_reviews_repository_created", "repository_id", text("created_at DESC")),
        Index("ix_reviews_repository_pr_created", "repository_id", "pr_number", text("created_at DESC")),
    )

    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    github_delivery_id: Mapped[UUID | None] = mapped_column(nullable=True, unique=True)
    
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str] = mapped_column(Text, nullable=False)
    head_branch: Mapped[str] = mapped_column(Text, nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    stage: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'received'"))

    files_changed: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))
    chunk_total: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))
    chunk_done: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_of: Mapped[UUID | None] = mapped_column(ForeignKey("reviews.id"), nullable=True)
    
    # 관계 설정 
    repository: Mapped["Repository"] = relationship(back_populates="reviews", lazy="raise")
    job: Mapped["Job | None"] = relationship(back_populates="review", lazy="raise", passive_deletes="all")
    files: Mapped[list["ReviewFile"]] = relationship(back_populates="review", lazy="raise", passive_deletes="all")
    issues: Mapped[list["ReviewIssue"]] = relationship(back_populates="review", foreign_keys="ReviewIssue.review_id", lazy="raise", passive_deletes="all")
    events: Mapped[list["ReviewEvent"]] = relationship(back_populates="review", lazy="raise", passive_deletes="all")

    retry_parent: Mapped["Review | None"] = relationship(remote_side="Review.id", back_populates="retries", lazy="raise")
    retries: Mapped[list["Review"]] = relationship(back_populates="retry_parent", lazy="raise", passive_deletes="all")
