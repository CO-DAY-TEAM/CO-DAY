# GitHub API 클라이언트
import asyncio
import base64
import time
from urllib.parse import quote

import httpx
import jwt

from coday_core.config import Settings, get_settings
from coday_core.errors import GitHubError, ServiceError


def segment(value: str) -> str:
    return quote(value, safe="")


def repo_path(full_name: str) -> str:
    owner, name = full_name.split("/", 1)
    return f"/repos/{segment(owner)}/{segment(name)}"


class GitHub:
    """GitHub API 호출·인증을 담당한다. 응답 유실 시 쓰기 결과 복구는 호출 측에서 처리한다."""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.AsyncClient(timeout=40, follow_redirects=False)
        self.tokens: dict[tuple[int, int | None], tuple[str, float]] = {}

    async def close(self):
        await self.client.aclose()

    def app_token(self) -> str:
        timestamp = int(time.time())
        return jwt.encode(
            {
                "iat": timestamp - 60,
                "exp": timestamp + 540,
                "iss": self.settings.github_app_id,
            },
            self.settings.github_private_key_path.read_text(),
            algorithm="RS256",
        )

    async def request(
        self,
        token: str,
        method: str,
        path: str,
        *,
        data=None,
        params=None,
        allow_missing=False,
    ):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("GitHub API 경로는 상대 경로여야 합니다.")
        attempts = self.settings.internal_retries + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = await self.client.request(
                    method,
                    "https://api.github.com" + path,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2026-03-10",
                    },
                    json=data,
                    params=params,
                )
            except httpx.TransportError as error:
                if attempt + 1 < attempts:
                    await asyncio.sleep(2**attempt)
                    continue
                raise GitHubError(0, True) from error
            if allow_missing and response.status_code == 404:
                return None
            if response.status_code == 204:
                return {}
            if response.is_success:
                return response.json()
            retryable = (
                response.status_code >= 500
                or response.status_code == 429
                or (
                    response.status_code == 403
                    and (
                        response.headers.get("x-ratelimit-remaining") == "0"
                        or "retry-after" in response.headers
                    )
                )
            )
            if retryable and attempt + 1 < attempts:
                await asyncio.sleep(min(float(response.headers.get("retry-after", 2**attempt)), 20))
                continue
            raise GitHubError(response.status_code, retryable)
        raise GitHubError(0, True)

    async def pages(
        self,
        token: str,
        path: str,
        *,
        key: str | None = None,
        params: dict | None = None,
        max_pages: int = 100,
    ):
        items = []
        for page in range(1, max_pages + 1):
            result = await self.request(
                token,
                "GET",
                path,
                params={**(params or {}), "per_page": 100, "page": page},
            )
            batch = result[key] if key else result
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise ServiceError(
            "github_page_limit",
            "GitHub 조회 한도에 도달했습니다. 운영 설정을 확인해 주세요.",
        )

    async def installation_token(
        self,
        installation_id: int,
        repository_id: int | None = None,
        force: bool = False,
    ):
        key = (installation_id, repository_id)
        cached = self.tokens.get(key)
        if cached and cached[1] > time.time() and not force:
            return cached[0]
        result = await self.request(
            self.app_token(),
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            data={"repository_ids": [repository_id]} if repository_id else {},
        )
        self.tokens[key] = (result["token"], time.time() + 3000)
        return result["token"]

    async def check_installation(self, installation_id: int, full_name: str | None = None):
        path = (
            repo_path(full_name) + "/installation"
            if full_name
            else f"/app/installations/{installation_id}"
        )
        result = await self.request(self.app_token(), "GET", path, allow_missing=True)
        if not result or result["id"] != installation_id or result.get("suspended_at"):
            raise ServiceError("access_removed", "GitHub App의 저장소 접근이 해제되었습니다.", 403)
        return result

    async def permission(self, token: str, full_name: str, login: str):
        path = f"{repo_path(full_name)}/collaborators/{segment(login)}"
        # public 저장소여도 대시보드 접근에는 GitHub에서 부여받은 저장소 권한이 필요하다.
        member = await self.request(token, "GET", path, allow_missing=True)
        if member is None:
            return "none"
        result = await self.request(token, "GET", path + "/permission")
        return result["permission"]

    async def file(self, token: str, full_name: str, path: str, sha: str) -> bytes:
        result = await self.request(
            token,
            "GET",
            f"{repo_path(full_name)}/contents/{segment(path)}",
            params={"ref": sha},
        )
        if (
            not isinstance(result, dict)
            or result.get("type") != "file"
            or result.get("submodule_git_url")
        ):
            raise ServiceError("unsupported_file", "일반 파일이 아닌 변경을 읽을 수 없습니다.")
        if result.get("size", 0) > self.settings.max_file_bytes:
            raise ServiceError(
                "file_limit",
                "파일 크기 처리 한도를 넘었습니다. 운영 설정 또는 제외 경로를 확인해 주세요.",
            )
        if result.get("encoding") != "base64":
            result = await self.request(
                token, "GET", f"{repo_path(full_name)}/git/blobs/{result['sha']}"
            )
        if result.get("encoding") != "base64":
            raise ServiceError("file_unavailable", "변경 파일의 전체 내용을 읽지 못했습니다.")
        content = base64.b64decode(result["content"])
        if len(content) > self.settings.max_file_bytes:
            raise ServiceError("file_limit", "파일 크기 처리 한도를 넘었습니다.")
        return content

    async def oauth(self, **data):
        try:
            response = await self.client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret.get_secret_value(),
                    **data,
                },
            )
            result = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ServiceError(
                "login_failed",
                "GitHub 로그인에 실패했습니다. 다시 로그인해 주세요.",
                401,
            ) from error
        if not response.is_success or "access_token" not in result:
            raise ServiceError(
                "login_failed", "GitHub 로그인이 만료되었거나 승인되지 않았습니다.", 401
            )
        return result
