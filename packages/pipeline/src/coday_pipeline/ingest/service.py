# 웹훅 이벤트를 검증하고 리뷰 작업을 큐에 등록
import hashlib
import hmac
import re

from coday_core.access import disable_access, upsert_installation, upsert_repository
from coday_core.db import transaction
from coday_core.db.models import Repository
from coday_core.errors import ServiceError
from coday_core.github import GitHub
from coday_core.queue import enqueue


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def apply_revocation(db, event: str, payload: dict):
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        return
    if event == "installation" and payload.get("action") in {"deleted", "suspend"}:
        disable_access(db, installation_id)
    if event == "installation_repositories" and payload.get("repositories_removed"):
        disable_access(db, installation_id, [r["id"] for r in payload["repositories_removed"]])


async def ingest(github: GitHub, delivery_id: str, event: str, payload: dict):
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        return
    if event == "installation" and payload.get("action") in {"deleted", "suspend"}:
        return
    if event in {"installation", "installation_repositories"}:
        data = await github.check_installation(installation_id)
        with transaction() as db:
            upsert_installation(db, data)
        token = await github.installation_token(installation_id)
        repositories = await github.pages(token, "/installation/repositories", key="repositories")
        with transaction() as db:
            active_ids = {repo["id"] for repo in repositories}
            from sqlalchemy import select

            previous = list(
                db.scalars(select(Repository).where(Repository.installation_id == installation_id))
            )
            disable_access(
                db,
                installation_id,
                [repo.id for repo in previous if repo.id not in active_ids],
            )
            for repo in repositories:
                upsert_repository(db, installation_id, repo)
        return
    if "repository" not in payload:
        return
    action = payload.get("action")
    comment = payload.get("comment", {})
    command = rf"@{re.escape(github.settings.github_app_slug)}\s+review"
    if event == "pull_request" and action in {"opened", "ready_for_review"}:
        pr_number, trigger, requester = payload["number"], "automatic", None
    elif (
        event == "issue_comment"
        and action == "created"
        and payload.get("issue", {}).get("pull_request")
        and comment["user"]["type"] != "Bot"
        and re.fullmatch(command, comment["body"].strip(), re.IGNORECASE)
    ):
        pr_number, trigger, requester = (
            payload["issue"]["number"],
            "manual",
            comment["user"]["login"],
        )
    else:
        # 리뷰 등록 대상이 아닌 웹훅은 GitHub를 호출하지 않고 끝낸다.
        return
    repository = payload["repository"]
    # 앱 삭제나 저장소 제외는 웹훅을 받는 즉시 DB에 반영된다.
    # 따라서 repo가 active 상태이고 같은 계정의 설치에 속하면 GitHub에 다시 확인하지 않는다.
    with transaction() as db:
        repo = db.get(Repository, repository["id"])
        should_check_installation = (
            repo is None or not repo.active or repo.installation_id != installation_id
        )
        if not should_check_installation:
            repo.full_name = repository["full_name"]
            repo.private = repository.get("private", True)
    if should_check_installation:
        data = await github.check_installation(installation_id, repository["full_name"])
        with transaction() as db:
            upsert_installation(db, data)
            upsert_repository(db, installation_id, repository)
    try:
        await enqueue(
            github, repository["id"], pr_number, delivery_id, trigger, requester=requester
        )
    except ServiceError as error:
        if trigger == "automatic" or error.code not in {
            "forbidden",
            "paused",
            "pr_closed",
            "daily_limit",
        }:
            raise
