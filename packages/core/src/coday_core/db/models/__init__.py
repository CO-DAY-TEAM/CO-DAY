# 데이터베이스 모델 모음
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Installation(Base):
    __tablename__ = "installations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger)
    login: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    installation_id: Mapped[int] = mapped_column(ForeignKey("installations.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(512))
    private: Mapped[bool] = mapped_column(Boolean)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    use_common: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PullRequest(Base):
    __tablename__ = "pull_requests"
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    head_sha: Mapped[str] = mapped_column(String(64))
    progress_comment_id: Mapped[int | None] = mapped_column(BigInteger)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_key: Mapped[str] = mapped_column(String(255), unique=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    pr_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512))
    head_sha: Mapped[str] = mapped_column(String(64))
    base_sha: Mapped[str] = mapped_column(String(64))
    settings: Mapped[dict] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(128))
    trigger: Mapped[str] = mapped_column(String(16))
    requester: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recoveries: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    publication: Mapped[list | None] = mapped_column(JSON)
    __table_args__ = (
        Index(
            "one_active_review_per_pr",
            "repository_id",
            "pr_number",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )


class UnitResult(Base):
    __tablename__ = "unit_results"
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    unit: Mapped[int] = mapped_column(Integer, primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)


class PostedFinding(Base):
    __tablename__ = "posted_findings"
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    pr_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    github_review_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    error_code: Mapped[str | None] = mapped_column(String(64))


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    login: Mapped[str] = mapped_column(String(255))
    token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthState(Base):
    __tablename__ = "oauth_states"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    verifier: Mapped[str] = mapped_column(String(128))
    return_to: Mapped[str] = mapped_column(String(2048), default="/")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
