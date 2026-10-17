from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from coday_core.db.base import (
    Base,
    CreatedAt,
    UpdatedAt,
    UUIDPrimaryKey,
)

if TYPE_CHECKING:
    from coday_core.db.models.issue_feedback import IssueFeedback

class User(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "users"

    github_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 관계 설정
    feedback: Mapped[list["IssueFeedback"]] = relationship(back_populates="user", lazy="raise", passive_deletes="all")