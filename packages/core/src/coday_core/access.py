from coday_contracts.settings import ReviewSettings
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from coday_core.db import transaction
from coday_core.db.models import Installation, Repository, Review, now
from coday_core.errors import ServiceError
from coday_core.github import GitHub, repo_path, segment

LEVEL = {"none": 0, "read": 1, "triage": 1, "write": 2, "maintain": 2, "admin": 3}


def effective_settings(repo: Repository, installation: Installation) -> ReviewSettings:
    return ReviewSettings.model_validate(
        installation.settings if repo.use_common else repo.settings or {}
    )


def disable_access(db, installation_id: int, repository_ids: list[int] | None = None):
    if repository_ids is None:
        install = db.get(Installation, installation_id)
        if install:
            install.active = False
    query = select(Repository).where(Repository.installation_id == installation_id)
    if repository_ids is not None:
        query = query.where(Repository.id.in_(repository_ids))
    ids = []
    for repo in db.scalars(query):
        repo.active = False
        ids.append(repo.id)
    db.execute(
        update(Review)
        .where(Review.repository_id.in_(ids), Review.status.in_(["queued", "running"]))
        .values(status="cancelled", error_code="access_removed", updated_at=now())
    )


def upsert_installation(db, data: dict) -> Installation:
    previous = db.scalar(
        select(Installation)
        .where(Installation.account_id == data["account"]["id"])
        .order_by(Installation.id.desc())
        .limit(1)
    )
    db.execute(
        insert(Installation)
        .values(
            id=data["id"],
            account_id=data["account"]["id"],
            login=data["account"]["login"],
            account_type=data["account"]["type"],
            settings=previous.settings if previous else ReviewSettings().model_dump(),
            paused=previous.paused if previous else False,
        )
        .on_conflict_do_nothing()
    )
    install = db.scalar(select(Installation).where(Installation.id == data["id"]).with_for_update())
    install.account_id = data["account"]["id"]
    install.login = data["account"]["login"]
    install.account_type = data["account"]["type"]
    install.active = not bool(data.get("suspended_at"))
    db.flush()
    return install


def upsert_repository(db, installation_id: int, data: dict) -> Repository:
    db.execute(
        insert(Repository)
        .values(
            id=data["id"],
            installation_id=installation_id,
            full_name=data["full_name"],
            private=data.get("private", True),
            use_common=True,
        )
        .on_conflict_do_nothing()
    )
    repo = db.scalar(select(Repository).where(Repository.id == data["id"]).with_for_update())
    # 저장소 owner가 바뀌면 이전 계정의 리뷰 지침을 새 owner에게 넘기지 않는다.
    old_install = db.get(Installation, repo.installation_id)
    new_install = db.get(Installation, installation_id)
    if old_install.account_id != new_install.account_id:
        repo.use_common, repo.settings = True, None
    repo.installation_id = installation_id
    repo.full_name = data["full_name"]
    repo.private = data.get("private", True)
    repo.active = True
    db.flush()
    return repo


async def repository_access(github: GitHub, repository_id: int, login: str, minimum="read"):
    with transaction() as db:
        repo = db.get(Repository, repository_id)
        install = db.get(Installation, repo.installation_id) if repo else None
        if not repo or not install or not repo.active or not install.active:
            raise ServiceError("access_removed", "접근 가능한 저장소가 아닙니다.", 403)
    try:
        await github.check_installation(install.id, repo.full_name)
    except ServiceError as error:
        if error.code == "access_removed":
            with transaction() as db:
                disable_access(db, install.id, [repo.id])
        raise
    token = await github.installation_token(install.id, repo.id)
    permission = await github.permission(token, repo.full_name, login)
    if LEVEL.get(permission, 0) < LEVEL[minimum]:
        raise ServiceError("forbidden", "이 작업에 필요한 저장소 권한이 없습니다.", 403)
    return repo, install, token, permission


async def owner_access(github: GitHub, installation_id: int, user_id: int, login: str):
    with transaction() as db:
        install = db.get(Installation, installation_id)
        if not install or not install.active:
            raise ServiceError("access_removed", "이 계정의 GitHub App에 접근할 수 없습니다.", 403)
    await github.check_installation(install.id)
    if install.account_type == "User":
        allowed = install.account_id == user_id
    else:
        token = await github.installation_token(install.id)
        member = await github.request(
            token,
            "GET",
            f"/orgs/{segment(install.login)}/memberships/{segment(login)}",
            allow_missing=True,
        )
        allowed = bool(member and member.get("role") == "admin" and member.get("state") == "active")
    if not allowed:
        raise ServiceError(
            "owner_required", "개인 계정 소유자 또는 조직 Owner만 변경할 수 있습니다.", 403
        )
    return install


async def synchronize(github: GitHub, user_token: str, login: str):
    """user access token으로 접근 가능한 installation과 저장소를 동기화한다.

    브라우저가 전달한 installation_id만으로 접근 권한을 복구하지 않는다.
    """
    installs = await github.pages(user_token, "/user/installations", key="installations")
    result = []
    for data in installs:
        if data.get("suspended_at"):
            continue
        await github.check_installation(data["id"])
        repos = await github.pages(
            user_token, f"/user/installations/{data['id']}/repositories", key="repositories"
        )
        with transaction() as db:
            install = upsert_installation(db, data)
        for item in repos:
            token = await github.installation_token(install.id, item["id"])
            permission = await github.permission(token, item["full_name"], login)
            if LEVEL.get(permission, 0) < 1:
                continue
            await github.check_installation(install.id, item["full_name"])
            # user access token으로 다시 조회해 현재 SSO와 인증·권한 조건도 확인한다.
            await github.request(user_token, "GET", repo_path(item["full_name"]))
            with transaction() as db:
                repo = upsert_repository(db, install.id, item)
            result.append((repo, install, permission))
    return result
