# GitHub OAuth 인증 라우트
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from coday_core.db import transaction
from coday_core.db.models import LoginSession, OAuthState, now
from coday_core.errors import ServiceError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from coday_api.dependencies import cipher, current_session, digest, mutation_session, user_token

router = APIRouter(prefix="/api/auth")


@router.get("/login")
async def login(request: Request, return_to: str = "/"):
    settings = request.app.state.settings
    if not settings.github_client_id:
        raise ServiceError(
            "not_configured", "운영자가 GitHub App 연결을 먼저 설정해야 합니다.", 503
        )
    if (
        not return_to.startswith("/")
        or return_to.startswith("//")
        or "\\" in return_to
        or len(return_to) > 2000
    ):
        return_to = "/"
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    with transaction() as db:
        db.execute(delete(OAuthState).where(OAuthState.expires_at < now()))
        db.execute(delete(LoginSession).where(LoginSession.expires_at < now()))
        db.add(
            OAuthState(
                id=digest(state),
                verifier=verifier,
                return_to=return_to,
                expires_at=now() + timedelta(minutes=10),
            )
        )
    params = {
        "client_id": settings.github_client_id,
        "state": state,
        "scope": "offline_access",
        "redirect_uri": settings.public_url.rstrip("/") + "/api/auth/callback",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode(),
        "code_challenge_method": "S256",
    }
    response = RedirectResponse("https://github.com/login/oauth/authorize?" + urlencode(params))
    response.set_cookie(
        "coday_oauth",
        state,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=600,
        path="/api/auth",
    )
    return response


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    if not state or not hmac.compare_digest(state, request.cookies.get("coday_oauth", "")):
        raise ServiceError(
            "oauth_state", "로그인 확인이 만료되었습니다. 다시 로그인해 주세요.", 400
        )
    with transaction() as db:
        saved = db.scalar(
            select(OAuthState).where(OAuthState.id == digest(state)).with_for_update()
        )
        if not saved or saved.expires_at < now():
            raise ServiceError(
                "oauth_state", "로그인 요청이 만료되었거나 이미 사용되었습니다.", 400
            )
        verifier, return_to = saved.verifier, saved.return_to
        db.delete(saved)
    settings = request.app.state.settings
    data = await request.app.state.github.oauth(
        code=code,
        code_verifier=verifier,
        redirect_uri=settings.public_url.rstrip("/") + "/api/auth/callback",
    )
    user = await request.app.state.github.request(data["access_token"], "GET", "/user")
    cookie = secrets.token_urlsafe(32)
    with transaction() as db:
        old = request.cookies.get("coday_session")
        if old:
            db.execute(delete(LoginSession).where(LoginSession.id == digest(old)))
        db.add(
            LoginSession(
                id=digest(cookie),
                user_id=user["id"],
                login=user["login"],
                token=cipher(request).encrypt(data["access_token"].encode()).decode(),
                refresh_token=cipher(request).encrypt(data["refresh_token"].encode()).decode()
                if data.get("refresh_token")
                else None,
                token_expires_at=now() + timedelta(seconds=data["expires_in"])
                if data.get("expires_in")
                else None,
                csrf=secrets.token_hex(32),
                expires_at=now() + timedelta(days=7),
            )
        )
    response = RedirectResponse(settings.public_url.rstrip("/") + return_to, status_code=303)
    response.delete_cookie("coday_oauth", path="/api/auth")
    response.set_cookie(
        "coday_session",
        cookie,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=7 * 86400,
    )
    return response


@router.get("/me")
async def me(request: Request):
    session = await current_session(request)
    token = await user_token(request, session)
    user = await request.app.state.github.request(token, "GET", "/user")
    if user["id"] != session.user_id:
        raise ServiceError("login_required", "다시 로그인해 주세요.", 401)
    return {
        "login": user["login"],
        "id": user["id"],
        "csrf": session.csrf,
        "install_url": f"https://github.com/apps/{request.app.state.settings.github_app_slug}/installations/new",
        "review_command": f"@{request.app.state.settings.github_app_slug} review",
    }


@router.post("/logout")
async def logout(request: Request):
    session = await mutation_session(request)
    with transaction() as db:
        db.execute(delete(LoginSession).where(LoginSession.id == session.id))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("coday_session")
    return response
