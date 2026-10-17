"""GitHub App 인증과 API 연동을 위한 공통 기능."""

import time
from pathlib import Path
import json
from urllib.parse import quote
from urllib.request import Request, urlopen
import jwt


def create_app_jwt(app_id: str, private_key_path: Path) -> str:
    if not app_id or not app_id.isascii() or not app_id.isdecimal():
        raise ValueError("GitHub App ID must be a numeric string.")

    private_key = private_key_path.read_bytes()
    now = int(time.time())
    payload = {
        "iss": app_id,
        "iat": now - 60,  # 컴퓨터 간 시계 차이를 고려한다.
        "exp": now + 540,  # 현재부터 9분 뒤 만료한다.
    }
    return jwt.encode(payload, private_key, algorithm="RS256")

# GitHub App ID 가져오기 
def get_installation_id(
    app_jwt: str,
    owner: str,
    repo: str,
) -> int:
    safe_owner = quote(owner, safe="")
    safe_repo = quote(repo, safe="")

    request = Request(
        url=(
            "https://api.github.com/repos/"
            f"{safe_owner}/{safe_repo}/installation"
        ),
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "CO-DAY-Act",
        },
        method="GET",
    )

    with urlopen(request, timeout=10) as response:
        installation_info = json.load(response)

    return installation_info["id"]

# GitHub App 토큰 가져오기 
def create_installation_token(app_jwt: str,installation_id: int,repo: str) -> str:
    payload = {
        "repositories": [repo],
        "permissions": {"pull_requests": "write"},
    }

    request = Request(
        url=(
            "https://api.github.com/app/installations/"
            f"{installation_id}/access_tokens"
        ),
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "CO-DAY-Act",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )

    with urlopen(request, timeout=10) as response:
        token_info = json.load(response)

    return token_info["token"]

# 인라인 코멘트를 실제로 등록하는 함수 
def post_review_comment(
    installation_token: str,
    owner: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    path: str,
    start_line: int,
    end_line: int,
    side: str,
    body: str,
) -> dict:
    safe_owner = quote(owner, safe="")
    safe_repo = quote(repo, safe="")

    payload = {
        "commit_id": commit_id,
        "path": path,
        "line": end_line,
        "side": side,
        "body": body,
    }

    if start_line < end_line:
        payload["start_line"] = start_line
        payload["start_side"] = side

    request = Request(
        url=(
            "https://api.github.com/repos/"
            f"{safe_owner}/{safe_repo}/pulls/{pr_number}/comments"
        ),
        headers={
            "Authorization": f"Bearer {installation_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "CO-DAY-Act",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )

    with urlopen(request, timeout=10) as response:
        return json.load(response)