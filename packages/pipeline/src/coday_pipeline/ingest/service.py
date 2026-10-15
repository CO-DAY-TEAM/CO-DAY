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
    data = await github.check_installation(installation_id)
    with transaction() as db:
        upsert_installation(db, data)
    if event in {"installation", "installation_repositories"}:
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
    if event not in {"pull_request", "issue_comment"} or "repository" not in payload:
        return
    repository = payload["repository"]
    await github.check_installation(installation_id, repository["full_name"])
    with transaction() as db:
        upsert_repository(db, installation_id, repository)
    if event == "pull_request" and payload.get("action") in {
        "opened",
        "ready_for_review",
    }:
        await enqueue(
            github,
            repository["id"],
            payload["number"],
            delivery_id,
            "automatic",
        )
    elif (
        event == "issue_comment"
        and payload.get("action") == "created"
        and payload.get("issue", {}).get("pull_request")
    ):
        comment = payload["comment"]
        command = rf"@{re.escape(github.settings.github_app_slug)}\s+review"
        if comment["user"]["type"] != "Bot" and re.fullmatch(
            command, comment["body"].strip(), re.IGNORECASE
        ):
            try:
                await enqueue(
                    github,
                    repository["id"],
                    payload["issue"]["number"],
                    delivery_id,
                    "manual",
                    requester=comment["user"]["login"],
                )
            except ServiceError as error:
                if error.code not in {"forbidden", "paused", "pr_closed"}:
                    raise
