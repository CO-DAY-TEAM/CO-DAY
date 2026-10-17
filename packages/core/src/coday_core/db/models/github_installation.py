from sqlalchemy import BigInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship 
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coday_core.db.models.repository import Repository

from coday_core.db.base import (
    Base,
    CreatedAt,
    UpdatedAt,
    UUIDPrimaryKey,
)

class GitHubInstallation(UUIDPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "github_installations"

    github_installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))

    # 관계 설정 (컬럼 생성 X)
    repositories: Mapped[list["Repository"]] = relationship(back_populates="installation", lazy="raise", passive_deletes="all")