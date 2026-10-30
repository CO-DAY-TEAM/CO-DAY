# 연결된 저장소 관리 라우트
from coday_core.access import effective_settings, owner_access, synchronize
from coday_core.errors import ServiceError
from fastapi import APIRouter, Request

from coday_api.dependencies import current_session, user_token

router = APIRouter(prefix="/api/repos")


@router.get("")
async def repositories(request: Request):
    session = await current_session(request)
    token = await user_token(request, session)
    visible = await synchronize(request.app.state.github, token, session.login)
    installations, repos = {}, []
    for repo, install, permission in visible:
        if install.id not in installations:
            can_manage = False
            try:
                await owner_access(
                    request.app.state.github, install.id, session.user_id, session.login
                )
                can_manage = True
            except ServiceError as error:
                if error.code != "owner_required":
                    raise
            installations[install.id] = {
                "id": install.id,
                "login": install.login,
                "account_type": install.account_type,
                "paused": install.paused,
                "settings": install.settings,
                "can_manage": can_manage,
            }
        repos.append(
            {
                "id": repo.id,
                "full_name": repo.full_name,
                "private": repo.private,
                "installation_id": install.id,
                "permission": permission,
                "use_common": repo.use_common,
                "settings": effective_settings(repo, install).model_dump(),
            }
        )
    return {"installations": list(installations.values()), "repositories": repos}
