# 리뷰 설정 관리 라우트
from coday_contracts.settings import ReviewSettings
from coday_core.access import effective_settings, owner_access
from coday_core.db import transaction
from coday_core.db.models import Installation, Repository, Review, now
from coday_core.errors import ServiceError
from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select, update

from coday_api.dependencies import authorized_repo, mutation_session, user_token

router = APIRouter(prefix="/api/settings")


class InstallationChange(BaseModel):
    settings: ReviewSettings
    paused: bool


class RepositoryChange(BaseModel):
    use_common: bool
    settings: ReviewSettings | None = None


def cancel_waiting(db, repository_ids: list[int], automatic_only=False):
    query = update(Review).where(
        Review.repository_id.in_(repository_ids), Review.status == "queued"
    )
    if automatic_only:
        # 사용자가 재시도한 자동 리뷰는 자동 리뷰 OFF 시 대기 취소 대상에서 제외한다.
        query = query.where(Review.trigger == "automatic", Review.attempt == 1)
    db.execute(query.values(status="cancelled", updated_at=now()))


@router.put("/installations/{installation_id}")
async def update_installation(installation_id: int, data: InstallationChange, request: Request):
    session = await mutation_session(request)
    await user_token(request, session)
    await owner_access(request.app.state.github, installation_id, session.user_id, session.login)
    with transaction() as db:
        install = db.scalar(
            select(Installation).where(Installation.id == installation_id).with_for_update()
        )
        if not install.active:
            raise ServiceError("access_removed", "연결이 해제되었습니다.", 403)
        old_automatic = ReviewSettings.model_validate(install.settings).automatic
        install.settings, install.paused = data.settings.model_dump(), data.paused
        repos = list(
            db.scalars(select(Repository).where(Repository.installation_id == installation_id))
        )
        if data.paused:
            cancel_waiting(db, [repo.id for repo in repos])
        elif old_automatic and not data.settings.automatic:
            cancel_waiting(db, [repo.id for repo in repos if repo.use_common], automatic_only=True)
    return {"saved": True}


@router.put("/repositories/{repository_id}")
async def update_repository(repository_id: int, data: RepositoryChange, request: Request):
    session = await mutation_session(request)
    repo, install, _, _ = await authorized_repo(request, repository_id, session, "admin")
    with transaction() as db:
        install = db.scalar(
            select(Installation).where(Installation.id == install.id).with_for_update()
        )
        repo = db.scalar(select(Repository).where(Repository.id == repository_id).with_for_update())
        if not install.active or not repo.active:
            raise ServiceError("access_removed", "연결이 해제되었습니다.", 403)
        previous = effective_settings(repo, install)
        if data.use_common:
            repo.use_common, repo.settings = True, None
        elif repo.use_common:
            repo.use_common, repo.settings = False, install.settings.copy()
        elif data.settings is not None:
            repo.settings = data.settings.model_dump()
        if previous.automatic and not effective_settings(repo, install).automatic:
            cancel_waiting(db, [repo.id], automatic_only=True)
    return {"saved": True}
