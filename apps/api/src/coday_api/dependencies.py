import hashlib
import hmac
from datetime import timedelta

from coday_core.access import repository_access
from coday_core.db import transaction
from coday_core.db.models import LoginSession, now
from coday_core.errors import ServiceError
from coday_core.github import repo_path
from cryptography.fernet import Fernet
from fastapi import Request
from sqlalchemy import select


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cipher(request: Request) -> Fernet:
    return Fernet(request.app.state.settings.token_encryption_key.get_secret_value().encode())


async def current_session(request: Request) -> LoginSession:
    cookie = request.cookies.get("coday_session", "")
    with transaction() as db:
        session = db.get(LoginSession, digest(cookie)) if cookie else None
        if not session or session.expires_at <= now():
            raise ServiceError("login_required", "GitHub로 로그인해 주세요.", 401)
        return session


async def mutation_session(request: Request) -> LoginSession:
    session = await current_session(request)
    if request.headers.get("origin") != request.app.state.settings.public_url.rstrip(
        "/"
    ) or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
        raise ServiceError(
            "csrf_failed", "요청 확인에 실패했습니다. 화면을 새로고침해 주세요.", 403
        )
    return session


async def user_token(request: Request, session: LoginSession):
    with transaction() as db:
        current = db.scalar(
            select(LoginSession).where(LoginSession.id == session.id).with_for_update()
        )
        if not current:
            raise ServiceError("login_required", "다시 로그인해 주세요.", 401)
        if current.token_expires_at and current.token_expires_at <= now() + timedelta(seconds=60):
            if not current.refresh_token:
                raise ServiceError(
                    "login_required", "GitHub 인증이 만료되었습니다. 다시 로그인해 주세요.", 401
                )
            data = await request.app.state.github.oauth(
                grant_type="refresh_token",
                refresh_token=cipher(request).decrypt(current.refresh_token.encode()).decode(),
            )
            current.token = cipher(request).encrypt(data["access_token"].encode()).decode()
            if data.get("refresh_token"):
                current.refresh_token = (
                    cipher(request).encrypt(data["refresh_token"].encode()).decode()
                )
            current.token_expires_at = (
                now() + timedelta(seconds=data["expires_in"]) if data.get("expires_in") else None
            )
        return cipher(request).decrypt(current.token.encode()).decode()


async def authorized_repo(
    request: Request, repository_id: int, session: LoginSession, minimum="read"
):
    token = await user_token(request, session)
    result = await repository_access(
        request.app.state.github, repository_id, session.login, minimum
    )
    await request.app.state.github.request(token, "GET", repo_path(result[0].full_name))
    return result
