from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, UniqueConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coday_core.db.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from coday_core.db.models.review import Review
    from coday_core.db.models.review_issue import ReviewIssue

class ReviewFile(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "review_files"

    # 제약 조건 및 인덱스 설정 
    __table_args__ = (
        UniqueConstraint("review_id", "file_path"), # 같은 실행에서 파일이 중복되는 것을 방지 
        UniqueConstraint("id", "review_id"), # 각 리뷰 파일은 고유한 ID를 가져야 함
        CheckConstraint("additions >= 0", name="additions_nonnegative"),
        CheckConstraint("deletions >= 0", name="deletions_nonnegative"),
    )

    review_id: Mapped[UUID] = mapped_column(ForeignKey("reviews.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    exclude_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))

    # 관계 설정
    review: Mapped["Review"] = relationship(back_populates="files", lazy="raise")
    issues: Mapped[list["ReviewIssue"]] = relationship(back_populates="review_file", foreign_keys="ReviewIssue.review_file_id", lazy="raise", passive_deletes="all")