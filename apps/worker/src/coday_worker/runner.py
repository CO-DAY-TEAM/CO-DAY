# 큐에서 리뷰 작업을 꺼내 파이프라인을 실행
import asyncio
import hashlib
import logging
from datetime import timedelta

from coday_contracts.review_input import ReviewInput
from coday_contracts.review_job import ReviewJob
from coday_contracts.review_result import ReviewResult
from coday_contracts.settings import ReviewSettings
from coday_core.access import disable_access, effective_settings
from coday_core.db import engine, transaction
from coday_core.db.models import Delivery, Installation, Repository, Review, UnitResult, now
from coday_core.errors import GitHubError, ServiceError, Stopped
from coday_core.github import GitHub, repo_path
from coday_pipeline.act.service import act, progress
from coday_pipeline.analyze import analyze
from coday_pipeline.ingest.service import ingest
from coday_pipeline.judge.service import judge
from sqlalchemy import and_, or_, select, text

logger = logging.getLogger(__name__)


def lock_key(repository_id: int, pr_number: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{repository_id}:{pr_number}".encode()).digest()[:8], "big", signed=True
    )


def claim():
    stale = now() - timedelta(seconds=120)
    eligible = or_(
        Review.status == "queued", and_(Review.status == "running", Review.heartbeat_at < stale)
    )
    with transaction() as db:
        candidates = list(
            db.scalars(select(Review).where(eligible).order_by(Review.created_at).limit(32))
        )
    for candidate in candidates:
        connection = engine().connect().execution_options(isolation_level="AUTOCOMMIT")
        key = lock_key(candidate.repository_id, candidate.pr_number)
        if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
            connection.close()
            continue
        try:
            with transaction() as db:
                review = db.scalar(
                    select(Review)
                    .where(Review.id == candidate.id, eligible)
                    .with_for_update(skip_locked=True)
                )
                if not review:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    connection.close()
                    continue
                if review.status == "running":
                    review.recoveries += 1
                repo = db.get(Repository, review.repository_id)
                install = db.get(Installation, repo.installation_id)
                if (
                    not repo.active
                    or not install.active
                    or install.paused
                    or (
                        review.trigger == "automatic"
                        and review.attempt == 1
                        and not effective_settings(repo, install).automatic
                        and review.status == "queued"
                    )
                ):
                    review.status = "cancelled"
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    connection.close()
                    continue
                review.status = "running"
                review.heartbeat_at = review.updated_at = now()
            pid = connection.scalar(text("SELECT pg_backend_pid()"))
            return candidate.id, connection, key, pid
        except BaseException:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            connection.close()
            raise
    return None


async def run_review(github: GitHub, review_id: str, connection=None, backend_pid=None):
    with transaction() as db:
        review = db.get(Review, review_id)
        repo = db.get(Repository, review.repository_id)
        installation_id = repo.installation_id
    token = ""

    async def guard(check_head=True):
        if (
            connection is not None
            and connection.scalar(text("SELECT pg_backend_pid()")) != backend_pid
        ):
            raise Stopped("lock_lost", "작업 잠금을 잃어 처리를 중단했습니다.")
        with transaction() as db:
            current = db.get(Review, review_id)
            current_repo = db.get(Repository, repo.id)
            install = db.get(Installation, installation_id)
            if current.status != "running":
                raise Stopped(
                    "superseded", "작업이 취소되었거나 최신 커밋 작업으로 대체되었습니다."
                )
            if (
                not current_repo.active
                or not install.active
                or current_repo.installation_id != installation_id
            ):
                raise Stopped("access_removed", "저장소 접근이 해제되었습니다.")
        try:
            await github.check_installation(installation_id, repo.full_name)
        except ServiceError as error:
            if error.code == "access_removed":
                with transaction() as db:
                    disable_access(db, installation_id, [repo.id])
                raise Stopped(error.code, error.message) from error
            raise
        if check_head:
            current_pr = await github.request(
                token, "GET", f"{repo_path(repo.full_name)}/pulls/{review.pr_number}"
            )
            if current_pr["head"]["sha"] != review.head_sha or current_pr["state"] != "open":
                with transaction() as db:
                    db.get(Review, review_id).status = "superseded"
                raise Stopped("head_changed", "PR이 closed 상태이거나 head SHA가 변경되었습니다.")

    async def reserve_ai_call():
        await guard()
        with transaction() as db:
            current = db.get(Review, review_id)
            if current.ai_calls >= github.settings.max_ai_calls:
                raise ServiceError(
                    "ai_call_limit",
                    "AI 호출 처리 한도에 도달했습니다. 운영 설정을 확인한 뒤 재시도해 주세요.",
                )
            current.ai_calls += 1

    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            with transaction() as db:
                current = db.get(Review, review_id)
                if current.status != "running":
                    return
                current.heartbeat_at = now()

    async def pipeline():
        nonlocal token
        if review.recoveries > github.settings.worker_recoveries:
            raise ServiceError(
                "worker_recovery_limit",
                "작업 복구 횟수 한도에 도달했습니다. 대시보드에서 재시도해 주세요.",
            )
        token = await github.installation_token(installation_id, repo.id, True)
        await guard()
        if review.stage == "queued":
            await progress(github, token, repo.full_name, review, "대기", github.settings)
        await guard()
        await progress(
            github,
            token,
            repo.full_name,
            review,
            "진행 중",
            github.settings,
            "변경 내용을 분석하고 있습니다.",
        )
        if review.input is None:
            owner, name = repo.full_name.split("/", 1)
            inputs = await analyze(
                ReviewJob(
                    owner=owner,
                    repo=name,
                    pr_number=review.pr_number,
                    head_sha=review.head_sha,
                ),
                ReviewSettings.model_validate(review.settings),
                github,
                token,
                guard,
            )
            with transaction() as db:
                current = db.get(Review, review_id)
                current.input, current.stage = inputs.model_dump(), "judge"
        else:
            inputs = ReviewInput.model_validate(review.input)
        with transaction() as db:
            existing_result = db.get(Review, review_id).result
        if existing_result is None:
            findings = []
            for index, chunk in enumerate(inputs.chunks):
                await guard()
                with transaction() as db:
                    saved = db.get(UnitResult, (review_id, index))
                if saved:
                    output = ReviewResult.model_validate(saved.result)
                else:
                    try:
                        output = await judge(
                            chunk,
                            inputs.related_files,
                            review.settings.get("instructions", ""),
                            github.settings.model_copy(update={"openai_model": review.model}),
                            reserve_ai_call,
                        )
                    except ServiceError:
                        raise
                    except Exception as error:
                        raise ServiceError(
                            "analysis_failed",
                            "AI 분석에 실패했습니다. 완료된 분석은 보존되어 재시도할 수 있습니다.",
                        ) from error
                    with transaction() as db:
                        db.add(
                            UnitResult(review_id=review_id, unit=index, result=output.model_dump())
                        )
                findings.extend(output.findings)
            # 모든 분석 단위의 지적을 모아 전체 리뷰 결과로 저장한다.
            result = {"findings": [finding.model_dump() for finding in findings]}
            with transaction() as db:
                current = db.get(Review, review_id)
                current.result, current.stage = result, "publish"
        await guard()
        await progress(
            github,
            token,
            repo.full_name,
            review,
            "진행 중",
            github.settings,
            "분석을 마쳤습니다. 리뷰를 게시하고 있습니다.",
        )
        await act(github, token, repo.full_name, review_id, guard)
        await guard()
        with transaction() as db:
            has_findings = bool(db.get(Review, review_id).result["findings"])
        description = (
            "리뷰 대상 없음"
            if not inputs.chunks
            else ("리뷰 결과를 게시했습니다." if has_findings else "지적 없음")
        )
        await progress(github, token, repo.full_name, review, "완료", github.settings, description)
        with transaction() as db:
            current = db.get(Review, review_id)
            if current.status == "running":
                current.status, current.stage, current.updated_at = "completed", "complete", now()
                current.error_code, current.error_message = None, None

    pulse = asyncio.create_task(heartbeat())
    try:
        await asyncio.wait_for(pipeline(), timeout=github.settings.job_timeout_seconds)
    except Stopped as error:
        # head SHA 변경이나 PR의 closed 상태로 중단된 리뷰에 대체 작업이 없으면 진행 댓글을 '실패'로 갱신한다.
        # 새 커밋은 자동 리뷰하지 않으므로, open 상태의 PR에 댓글로 새 리뷰를 요청하도록 안내한다.
        if error.code in {"head_changed", "superseded"}:
            try:
                with transaction() as db:
                    current_repo = db.get(Repository, repo.id)
                    install = db.get(Installation, installation_id)
                    allowed = current_repo.active and install.active
                    replacement = db.scalar(
                        select(Review)
                        .where(
                            Review.repository_id == repo.id,
                            Review.pr_number == review.pr_number,
                            Review.status.in_(["queued", "running"]),
                            Review.id != review_id,
                        )
                        .order_by(Review.created_at.desc())
                        .limit(1)
                    )
                if allowed:
                    await github.check_installation(installation_id, repo.full_name)
                    if replacement:
                        await progress(
                            github,
                            token,
                            repo.full_name,
                            replacement,
                            "대기",
                            github.settings,
                            "최신 커밋의 리뷰를 준비하고 있습니다.",
                        )
                    else:
                        await progress(
                            github,
                            token,
                            repo.full_name,
                            review,
                            "실패",
                            github.settings,
                            f"PR이 closed 상태이거나 head SHA가 변경되어 실행을 중단했습니다. open 상태의 PR에 @{github.settings.github_app_slug} review 댓글로 새 리뷰를 요청해 주세요.",
                        )
            except Exception:
                logger.warning("review=%s stopped_status_not_published", review_id)
    except Exception as error:
        if isinstance(error, TimeoutError):
            error = ServiceError(
                "timeout", "리뷰 처리 시간 한도를 넘었습니다. 저장된 결과로 재시도할 수 있습니다."
            )
        elif not isinstance(error, ServiceError):
            logger.error("review=%s unexpected_error=%s", review_id, type(error).__name__)
            error = ServiceError(
                "internal_error", "서비스 처리 중 오류가 발생했습니다. 잠시 후 재시도해 주세요."
            )
        # 오류 안내에는 원본 코드, 토큰, 외부 API 응답 본문을 포함하지 않는다.
        try:
            await guard()
            await progress(
                github, token, repo.full_name, review, "실패", github.settings, error.message
            )
        except Exception:
            logger.warning("review=%s failure_status_not_published", review_id)
        with transaction() as db:
            current = db.get(Review, review_id)
            if current.status == "running":
                current.status, current.error_code, current.error_message = (
                    "failed",
                    error.code,
                    error.message,
                )
                current.updated_at = now()
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)


async def process_delivery(github: GitHub) -> bool:
    with transaction() as db:
        delivery = db.scalar(
            select(Delivery)
            .where(Delivery.status.in_(["queued", "processing"]), Delivery.available_at <= now())
            .order_by(Delivery.available_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not delivery:
            return False
        delivery.status = "processing"
        delivery.attempts += 1
        delivery.available_at = now() + timedelta(seconds=180)
    try:
        await asyncio.wait_for(
            ingest(github, delivery.id, delivery.event, delivery.payload), timeout=150
        )
    except Exception as error:
        transient = isinstance(error, (TimeoutError, GitHubError))
        with transaction() as db:
            current = db.get(Delivery, delivery.id)
            current.status = "queued" if transient and delivery.attempts < 5 else "failed"
            current.available_at = now() + timedelta(seconds=min(2**delivery.attempts, 60))
            current.error_code = error.code if isinstance(error, ServiceError) else "ingest_error"
        logger.warning("delivery=%s failure=%s", delivery.id, type(error).__name__)
    else:
        with transaction() as db:
            db.get(Delivery, delivery.id).status = "completed"
    return True


async def worker_loop(github: GitHub):
    while True:
        try:
            await process_delivery(github)
            claimed = claim()
            if not claimed:
                await asyncio.sleep(1)
                continue
            review_id, connection, key, pid = claimed
            try:
                await run_review(github, review_id, connection, pid)
            finally:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                finally:
                    connection.close()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("worker_error=%s", type(error).__name__)
            await asyncio.sleep(5)
