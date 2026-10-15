# 작업 큐 연동
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from coday_core.access import effective_settings, repository_access
from coday_core.db import transaction
from coday_core.db.models import Installation, PullRequest, Repository, Review, now
from coday_core.errors import ServiceError
from coday_core.github import GitHub, repo_path


async def enqueue(
    github: GitHub,
    repository_id: int,
    number: int,
    request_key: str,
    trigger: str,
    requester: str | None = None,
):
    if requester:
        await repository_access(github, repository_id, requester, "write")
    with transaction() as db:
        repo = db.get(Repository, repository_id)
        if not repo:
            return None
        install = db.scalar(
            select(Installation).where(Installation.id == repo.installation_id).with_for_update()
        )
        db.refresh(repo)
        if not install.active or not repo.active:
            return None
        if install.paused:
            raise ServiceError(
                "paused",
                "전체 중지 상태입니다. 개인 계정 소유자 또는 조직 Owner가 중지를 해제한 뒤 요청해 주세요.",
            )
        settings = effective_settings(repo, install)
        if trigger == "automatic" and not settings.automatic:
            return None
        existing = db.scalar(select(Review).where(Review.request_key == request_key))
        if existing:
            return existing.id
        # installation 단위 DB 잠금으로 실행 기록 확인과 생성을 순서대로 처리한다.
        # failed·cancelled를 포함해 자동·수동 실행 기록이 있으면 자동 리뷰를 추가하지 않는다.
        if trigger == "automatic" and db.scalar(
            select(Review.id)
            .where(
                Review.repository_id == repo.id,
                Review.pr_number == number,
            )
            .limit(1)
        ):
            return None
        await github.check_installation(install.id, repo.full_name)
        token = await github.installation_token(install.id, repo.id)
        pr = await github.request(token, "GET", f"{repo_path(repo.full_name)}/pulls/{number}")
        if pr["state"] != "open":
            raise ServiceError("pr_closed", "open 상태의 PR에서 리뷰를 요청해 주세요.")
        if trigger == "automatic" and (
            pr["draft"]
            or pr["user"]["type"] == "Bot"
            or pr["user"]["login"].endswith("[bot]")
            or not pr["head"]["repo"]
            or pr["head"]["repo"]["id"] != repo.id
        ):
            return None
        head = pr["head"]["sha"]
        db.execute(
            insert(PullRequest)
            .values(repository_id=repo.id, number=number, head_sha=head)
            .on_conflict_do_nothing()
        )
        pull = db.scalar(
            select(PullRequest)
            .where(PullRequest.repository_id == repo.id, PullRequest.number == number)
            .with_for_update()
        )
        pull.head_sha = head
        db.execute(
            update(Review)
            .where(
                Review.repository_id == repo.id,
                Review.pr_number == number,
                Review.status.in_(["queued", "running"]),
                Review.head_sha != head,
            )
            .values(status="superseded", updated_at=now())
        )
        active = db.scalar(
            select(Review).where(
                Review.repository_id == repo.id,
                Review.pr_number == number,
                Review.status.in_(["queued", "running"]),
            )
        )
        if active:
            return active.id
        review = Review(
            request_key=request_key,
            repository_id=repo.id,
            pr_number=number,
            title=pr["title"][:512],
            head_sha=head,
            base_sha=pr["base"]["sha"],
            settings=settings.model_dump(),
            model=github.settings.openai_model,
            trigger=trigger,
            requester=requester,
        )
        db.add(review)
        db.flush()
        return review.id


async def retry_review(github: GitHub, review_id: str, login: str):
    with transaction() as db:
        review = db.get(Review, review_id)
        if not review:
            raise ServiceError("not_found", "리뷰를 찾을 수 없습니다.", 404)
    repo, install, token, _ = await repository_access(github, review.repository_id, login, "write")
    with transaction() as db:
        install = db.scalar(
            select(Installation).where(Installation.id == install.id).with_for_update()
        )
        review = db.scalar(select(Review).where(Review.id == review_id).with_for_update())
        if install.paused:
            raise ServiceError("paused", "전체 중지 상태입니다. 중지를 해제한 뒤 재시도해 주세요.")
        if review.status != "failed":
            raise ServiceError("not_failed", "실패한 리뷰만 재시도할 수 있습니다.")
        pr = await github.request(
            token, "GET", f"{repo_path(repo.full_name)}/pulls/{review.pr_number}"
        )
        if pr["state"] != "open" or pr["head"]["sha"] != review.head_sha:
            raise ServiceError(
                "head_changed",
                "PR이 closed 상태이거나 새 커밋 등으로 head SHA가 변경되었습니다. open 상태의 PR에서 새 리뷰를 요청해 주세요.",
            )
        if db.scalar(
            select(Review.id).where(
                Review.repository_id == repo.id,
                Review.pr_number == review.pr_number,
                Review.status.in_(["queued", "running"]),
            )
        ):
            raise ServiceError(
                "already_running", "이 PR에는 이미 대기 또는 진행 중인 리뷰가 있습니다."
            )
        if review.stage in {"judge", "publish", "complete"} and review.input is None:
            raise ServiceError(
                "input_missing",
                "저장된 입력이 없어 재개할 수 없습니다. PR에서 새 리뷰를 요청해 주세요.",
            )
        review.status, review.error_code, review.error_message = "queued", None, None
        review.attempt += 1
        review.recoveries = 0
        review.heartbeat_at = None
        review.updated_at = now()
        # 재시도 시 AI 호출 횟수를 초기화하고, 성공한 분석 단위는 재사용한다.
        review.ai_calls = 0
        return review.id
