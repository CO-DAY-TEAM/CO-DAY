from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from coday_core.db.models.github_installation import GitHubInstallation
from sqlalchemy import Boolean, BigInteger, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from coday_core.db.models.github_installation import GitHubInstallation
    from coday_core.db.models.review import Review

from coday_core.db.base import (
    Base,
    CreatedAt,
    UpdatedAt,
    UUIDPrimaryKey,
)

class Repository(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "repositories"

    # 제약 조건 및 인덱스 설정 
    __table_args__ = (
        Index("ix_repositories_installation_id", "installation_id"),
    )

    installation_id: Mapped[UUID] = mapped_column(ForeignKey("github_installations.id"), nullable=False)
    github_repo_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)  
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # 관계 설정 (컬럼 생성 X)
    installation: Mapped[GitHubInstallation] = relationship("GitHubInstallation", back_populates="repositories", lazy="raise")
    reviews: Mapped[list["Review"]] = relationship(back_populates="repository",lazy="raise",passive_deletes="all",)