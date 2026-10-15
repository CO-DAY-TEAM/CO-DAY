# 리뷰 조회 라우트
from coday_core.access import synchronize
from coday_core.db import transaction
from coday_core.db.models import PostedFinding, Repository, Review
from coday_core.errors import ServiceError
from coday_core.queue import retry_review
from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from coday_api.dependencies import authorized_repo, current_session, mutation_session, user_token

router = APIRouter(prefix="/api/reviews")


def serialize(review: Review, repo: Repository):
    status, error = review.status, review.error_message
    if status in {"cancelled", "superseded"}:
        status = "failed"
        error = "중단된 리뷰입니다. open 상태의 PR에서 새 리뷰를 요청해 주세요."
    return {
        "id": review.id,
        "repository_id": review.repository_id,
        "repository": repo.full_name,
        "pr_number": review.pr_number,
        "title": review.title,
        "head_sha": review.head_sha,
        "status": status,
        "error": error,
        "can_resume": review.status == "failed",
        "created_at": review.created_at.isoformat(),
        "attempt": review.attempt,
        "github_url": f"https://github.com/{repo.full_name}/pull/{review.pr_number}",
    }


@router.get("")
async def list_reviews(
    request: Request, repository_id: int | None = None, page: int = Query(default=1, ge=1)
):
    session = await current_session(request)
    if repository_id is not None:
        repo, _, _, permission = await authorized_repo(request, repository_id, session)
        visible = [(repo, None, permission)]
    else:
        visible = await synchronize(
            request.app.state.github, await user_token(request, session), session.login
        )
    repo_map = {repo.id: (repo, permission) for repo, _, permission in visible}
    ids = list(repo_map)
    with transaction() as db:
        query = select(Review).where(
            Review.repository_id.in_(ids),
            Review.status.in_(["queued", "running", "completed", "failed"]),
        )
        reviews = list(
            db.scalars(query.order_by(Review.created_at.desc()).offset((page - 1) * 30).limit(31))
        )
        reviewed = (
            select(Review.repository_id, Review.pr_number)
            .where(Review.repository_id.in_(ids), Review.status == "completed")
            .distinct()
            .subquery()
        )
        count = db.scalar(select(func.count()).select_from(reviewed))
        types = dict(
            db.execute(
                select(PostedFinding.category, func.count())
                .where(PostedFinding.repository_id.in_(ids))
                .group_by(PostedFinding.category)
            ).all()
        )
    return {
        "reviews": [
            {
                **serialize(review, repo_map[review.repository_id][0]),
                "can_retry": repo_map[review.repository_id][1] in {"write", "maintain", "admin"},
            }
            for review in reviews[:30]
        ],
        "has_more": len(reviews) > 30,
        "stats": {"reviewed_prs": count, "findings": sum(types.values()), "categories": types},
    }


@router.get("/{review_id}")
async def get_review(review_id: str, request: Request):
    session = await current_session(request)
    with transaction() as db:
        review = db.get(Review, review_id)
        if not review:
            raise ServiceError("not_found", "리뷰를 찾을 수 없습니다.", 404)
    repo, _, _, _ = await authorized_repo(request, review.repository_id, session)
    return serialize(review, repo)


@router.post("/{review_id}/retry")
async def retry(review_id: str, request: Request):
    session = await mutation_session(request)
    with transaction() as db:
        review = db.get(Review, review_id)
        if not review:
            raise ServiceError("not_found", "리뷰를 찾을 수 없습니다.", 404)
    await authorized_repo(request, review.repository_id, session, "write")
    return {"id": await retry_review(request.app.state.github, review_id, session.login)}
