import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import timedelta

import pytest
from coday_api.main import app
from coday_contracts.review_input import ReviewInput
from coday_contracts.review_result import Finding, ReviewResult
from coday_contracts.settings import ReviewSettings
from coday_core.access import (
    repository_access,
    upsert_installation,
    upsert_repository,
)
from coday_core.config import Settings
from coday_core.db import transaction
from coday_core.db.models import (
    Delivery,
    Installation,
    PostedFinding,
    Repository,
    Review,
    UnitResult,
    now,
)
from coday_core.errors import GitHubError, ServiceError
from coday_core.queue import enqueue, retry_review
from coday_pipeline.analyze.chunker import chunks
from coday_pipeline.analyze.diff_parser import parse_patch
from coday_pipeline.ingest.service import ingest
from coday_worker import runner
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

pytestmark = pytest.mark.usefixtures("db")


class FakeGitHub:
    def __init__(self):
        self.settings = Settings(
            _env_file=None,
            github_app_slug="co-day-review",
            internal_retries=0,
            related_file_count=0,
        )
        self.head, self.active, self.permission_value = "head1", True, "admin"
        self.remote_reviews, self.comments = [], []
        self.lose_response = False
        self.post_count = 0
        self.draft, self.fork, self.bot = False, False, False

    async def check_installation(self, installation_id, full_name=None):
        if not self.active:
            raise ServiceError("access_removed", "접근 해제", 403)
        return {"id": installation_id, "account": {"id": 10, "login": "owner", "type": "User"}}

    async def installation_token(self, *args):
        return "test-token"

    async def permission(self, *args):
        return self.permission_value

    async def request(self, token, method, path, **kwargs):
        if path.endswith("/pulls/1"):
            return {
                "state": "open",
                "draft": self.draft,
                "title": "테스트 PR",
                "changed_files": 1,
                "user": {"type": "Bot" if self.bot else "User", "login": "author"},
                "head": {"sha": self.head, "repo": {"id": 999 if self.fork else 20}},
                "base": {"sha": "base"},
            }
        if "/issues/comments/" in path:
            comment = next(
                item for item in self.comments if item["id"] == int(path.rsplit("/", 1)[1])
            )
            comment.update(kwargs["data"])
            return comment
        if path.endswith("/comments") and method == "POST":
            comment = {
                "id": len(self.comments) + 1,
                "user": {"login": self.settings.bot_login},
                **kwargs["data"],
            }
            self.comments.append(comment)
            return comment
        if path.endswith("/reviews") and method == "POST":
            self.post_count += 1
            result = {
                "id": self.post_count,
                "user": {"login": self.settings.bot_login},
                "state": "COMMENTED",
                **kwargs["data"],
            }
            self.remote_reviews.append(result)
            if self.lose_response:
                self.lose_response = False
                raise GitHubError(0, True)
            return result
        raise AssertionError((method, path))

    async def pages(self, token, path, **kwargs):
        if path.endswith("/files"):
            return [
                {
                    "filename": "calc.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "changes": 2,
                    "patch": "@@ -1 +1 @@\n-x = 0\n+x = 1 / 0\n",
                }
            ]
        if path.endswith("/reviews"):
            return self.remote_reviews
        if path.endswith("/comments"):
            return self.comments
        raise AssertionError(path)


@pytest.fixture
def github():
    with transaction() as db:
        upsert_installation(db, {"id": 1, "account": {"id": 10, "login": "owner", "type": "User"}})
        upsert_repository(db, 1, {"id": 20, "full_name": "owner/test", "private": True})
    return FakeGitHub()


def finding(path="calc.py", line=1):
    return Finding(
        category="bug",
        importance="important",
        title="0으로 나누기",
        condition="이 경로에서 나눗셈을 실행하면 예외가 발생합니다.",
        evidence="분모가 0입니다.",
        recommendation="분모를 확인하세요.",
        path=path,
        line=line,
        side="RIGHT",
        start_line=None,
        suggestion="x = 0",
    )


@contextmanager
def claimed_review():
    claimed = runner.claim()
    try:
        yield claimed
    finally:
        if claimed is not None:
            _, connection, key, _ = claimed
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            finally:
                connection.close()


async def execute(github, review_id):
    with claimed_review() as claimed:
        assert claimed and claimed[0] == review_id
        _, connection, _, pid = claimed
        await runner.run_review(github, review_id, connection, pid)


# 유효한 서명의 webhook만 접수하고, 같은 delivery로 리뷰를 한 번만 큐에 넣는지 확인한다.
async def test_signed_webhook_queues_one_review_per_delivery(github):
    payload = {
        "installation": {"id": 1},
        "repository": {"id": 20, "full_name": "owner/test", "private": True},
        "action": "opened",
        "number": 1,
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        app.state.settings = Settings(_env_file=None, github_webhook_secret="test-secret")
        headers = {
            "x-github-event": "pull_request",
            "x-github-delivery": "one",
            "x-hub-signature-256": signature,
        }
        assert (
            client.post(
                "/api/webhooks/github",
                content=raw,
                headers={**headers, "x-hub-signature-256": "bad"},
            ).status_code
            == 401
        )
        assert client.post("/api/webhooks/github", content=raw, headers=headers).status_code == 202
        assert client.post("/api/webhooks/github", content=raw, headers=headers).status_code == 202
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Delivery)) == 1
    await runner.process_delivery(github)
    with transaction() as db:
        review = db.scalar(select(Review))
        assert db.scalar(select(func.count()).select_from(Review)) == 1
        assert review.status == "queued"
        assert review.trigger == "automatic"


# 수동 재리뷰는 현재 head를 새로 분석하고, 이전 리뷰에 있던 문제도 다시 게시하는지 확인한다.
@pytest.mark.parametrize("next_head", ["head1", "head2"])
async def test_manual_review_reanalyzes_and_republishes_current_head(
    github, monkeypatch, next_head
):
    calls = []

    async def judge(*args):
        calls.append(github.head)
        return ReviewResult(findings=[finding(), finding()])

    monkeypatch.setattr(runner, "judge", judge)
    first = await enqueue(github, 20, 1, "automatic-first", "automatic")
    await execute(github, first)
    with transaction() as db:
        assert db.get(Review, first).status == "completed"
        assert db.scalar(select(func.count()).select_from(PostedFinding)) == 1
    assert len(github.comments) == 1
    assert "완료" in github.comments[0]["body"]
    assert github.remote_reviews[0]["event"] == "COMMENT"
    assert github.remote_reviews[0]["commit_id"] == "head1"
    github.head = next_head
    second = await enqueue(github, 20, 1, "manual-second", "manual", "owner")
    await execute(github, second)
    assert calls == ["head1", next_head]
    assert github.remote_reviews[1]["commit_id"] == next_head
    assert len(github.remote_reviews[1]["comments"]) == 1
    assert github.remote_reviews[1]["comments"] == github.remote_reviews[0]["comments"]
    with transaction() as db:
        assert db.get(Review, second).status == "completed"
        assert db.scalar(select(func.count()).select_from(PostedFinding)) == 2


# 실패 후 재시도하면 완료된 분석을 재사용하고 최초 설정을 유지하는지 확인한다.
async def test_retry_reuses_successful_units_and_frozen_configuration(github, monkeypatch):
    review_id = await enqueue(github, 20, 1, "retry", "manual", "owner")
    parts = chunks("a.py", "added", parse_patch("@@ -0,0 +1 @@\n+x = 1\n"), 1000) + chunks(
        "b.py", "added", parse_patch("@@ -0,0 +1 @@\n+y = 2\n"), 1000
    )
    with transaction() as db:
        review = db.get(Review, review_id)
        review.input = ReviewInput(chunks=parts, analyzed_files=["a.py", "b.py"]).model_dump()
        review.stage = "judge"
    calls = []

    async def broken(chunk, related, instructions, settings, reserve_attempt):
        calls.append(chunk.file_path)
        if chunk.file_path == "b.py":
            raise RuntimeError("재시도 확인을 위해 발생시킨 오류")
        return ReviewResult()

    monkeypatch.setattr(runner, "judge", broken)
    await execute(github, review_id)
    with transaction() as db:
        assert db.get(Review, review_id).status == "failed"
        assert db.scalar(select(func.count()).select_from(UnitResult)) == 1
        install = db.get(Installation, 1)
        install.settings = {
            **install.settings,
            "instructions": "변경된 리뷰 지침",
            "automatic": False,
        }
    assert not github.remote_reviews

    async def recovered(chunk, related, instructions, settings, reserve_attempt):
        calls.append(chunk.file_path)
        assert instructions == ""
        return ReviewResult()

    monkeypatch.setattr(runner, "judge", recovered)
    await retry_review(github, review_id, "owner")
    await execute(github, review_id)
    assert calls == ["a.py", "b.py", "b.py"]
    assert len(github.remote_reviews) == 1
    with transaction() as db:
        assert db.get(Review, review_id).status == "completed"


# 게시 응답이 유실되어 재시도해도 리뷰를 중복 게시하거나 통계를 중복 집계하지 않는지 확인한다.
async def test_lost_publication_response_recovers_without_duplicate(github, monkeypatch):
    async def judge(*args):
        return ReviewResult(findings=[finding()])

    monkeypatch.setattr(runner, "judge", judge)
    review_id = await enqueue(github, 20, 1, "lost", "automatic")
    github.lose_response = True
    await execute(github, review_id)
    with transaction() as db:
        assert db.get(Review, review_id).status == "failed"
    await retry_review(github, review_id, "owner")
    await execute(github, review_id)
    assert github.post_count == 1
    with transaction() as db:
        assert db.get(Review, review_id).status == "completed"
        assert db.scalar(select(func.count()).select_from(PostedFinding)) == 1


# opened·ready_for_review로 최초 한 번만 자동 리뷰하고, 이후에는 댓글 요청으로 실행하는지 확인한다.
@pytest.mark.parametrize("initially_draft", [False, True])
async def test_pr_automatically_reviews_once_then_requires_comment(github, initially_draft):
    payload = {
        "installation": {"id": 1},
        "repository": {"id": 20, "full_name": "owner/test", "private": True},
        "number": 1,
    }
    for action in ("synchronize", "reopened"):
        await ingest(github, f"before-{action}", "pull_request", {**payload, "action": action})
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 0

    github.draft = initially_draft
    await ingest(github, "opened", "pull_request", {**payload, "action": "opened"})
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == (0 if initially_draft else 1)
    if initially_draft:
        github.draft = False
        await ingest(github, "ready", "pull_request", {**payload, "action": "ready_for_review"})
    with transaction() as db:
        first = db.scalar(select(Review))
        assert first.trigger == "automatic"
        first.status = "completed"

    for head in ("head1", "head2"):
        github.head = head
        for action in ("opened", "ready_for_review", "synchronize", "reopened"):
            await ingest(github, f"{head}-{action}", "pull_request", {**payload, "action": action})
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 1

    await ingest(
        github,
        "manual-comment",
        "issue_comment",
        {
            **payload,
            "action": "created",
            "issue": {"number": 1, "pull_request": {"url": "https://example.test/pulls/1"}},
            "comment": {
                "user": {"type": "User", "login": "owner"},
                "body": "@co-day-review review",
            },
        },
    )
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 2
        manual = db.scalar(select(Review).where(Review.trigger == "manual"))
        assert manual.head_sha == "head2"
        assert manual.status == "queued"


# 수동 리뷰 기록이 있으면 자동 리뷰를 켠 뒤 ready_for_review 이벤트가 와도 자동 실행하지 않는지 확인한다.
async def test_manual_review_then_enable_automatic_and_ready_does_not_run(github):
    github.draft = True
    with transaction() as db:
        db.get(Installation, 1).settings = ReviewSettings(automatic=False).model_dump()
    first = await enqueue(github, 20, 1, "manual-first", "manual", "owner")
    with transaction() as db:
        db.get(Review, first).status = "completed"
        db.get(Installation, 1).settings = ReviewSettings(automatic=True).model_dump()

    github.draft = False
    for head in ("head1", "head2"):
        github.head = head
        await ingest(
            github,
            f"ready-{head}",
            "pull_request",
            {
                "installation": {"id": 1},
                "repository": {"id": 20, "full_name": "owner/test", "private": True},
                "number": 1,
                "action": "ready_for_review",
            },
        )
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 1


# 최초 리뷰가 failed·cancelled여도 head 변경이나 ready_for_review로 자동 리뷰를 반복하지 않는지 확인한다.
@pytest.mark.parametrize("status", ["failed", "cancelled"])
async def test_unsuccessful_first_review_does_not_enable_another_automatic_run(github, status):
    first = await enqueue(github, 20, 1, "first", "automatic")
    with transaction() as db:
        db.get(Review, first).status = status
    assert await enqueue(github, 20, 1, "ready-again", "automatic") is None
    github.head = "head2"
    assert await enqueue(github, 20, 1, "new-head-ready", "automatic") is None
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 1


# 같은 head의 중복 요청을 합치고, 최신 head로 작업이 교체되어도 PR 잠금이 유지되는지 확인한다.
async def test_manual_latest_head_duplicate_and_worker_lock(github):
    first = await enqueue(github, 20, 1, "a", "automatic")
    assert await enqueue(github, 20, 1, "b", "manual", "owner") == first
    with claimed_review() as claimed:
        assert claimed and claimed[0] == first
        with transaction() as db:
            db.get(Review, first).heartbeat_at = now() - timedelta(minutes=5)
        with claimed_review() as duplicate:
            assert duplicate is None
        github.head = "head2"
        second = await enqueue(github, 20, 1, "c", "manual", "owner")
        assert second != first
        with claimed_review() as replacement:
            assert replacement is None  # 작업이 교체되어도 PR 단위 advisory lock은 유지된다.
        with transaction() as db:
            assert db.get(Review, first).status == "superseded"
    with claimed_review() as next_claim:
        assert next_claim and next_claim[0] == second


# draft·fork·bot PR은 자동 리뷰를 건너뛰고, Write 이상 권한으로만 수동 요청할 수 있는지 확인한다.
@pytest.mark.parametrize("condition", ["draft", "fork", "bot"])
async def test_draft_fork_and_bot_require_authorized_manual_review(github, condition):
    setattr(github, condition, True)
    assert await enqueue(github, 20, 1, "auto", "automatic") is None
    github.permission_value = "read"
    with pytest.raises(ServiceError, match="권한"):
        await enqueue(github, 20, 1, "manual-read", "manual", "reader")
    github.permission_value = "write"
    assert await enqueue(github, 20, 1, "manual-write", "manual", "writer")


# 전체 중지를 켜도 진행 중인 리뷰는 완료하고, 새 요청은 차단하는지 확인한다.
async def test_pause_blocks_new_requests_but_running_review_completes(github, monkeypatch):
    review_id = await enqueue(github, 20, 1, "pause", "automatic")

    async def judge(*args):
        with transaction() as db:
            db.get(Installation, 1).paused = True
        return ReviewResult()

    monkeypatch.setattr(runner, "judge", judge)
    await execute(github, review_id)
    with transaction() as db:
        assert db.get(Review, review_id).status == "completed"
    with pytest.raises(ServiceError, match="중지"):
        await enqueue(github, 20, 1, "blocked", "manual", "owner")


# head가 바뀌면 이전 head를 대상으로 한 실패 리뷰의 재시도를 거부하는지 확인한다.
async def test_head_change_blocks_retry_of_failed_review(github):
    review_id = await enqueue(github, 20, 1, "original", "automatic")
    with transaction() as db:
        db.get(Review, review_id).status = "failed"
    github.head = "head2"
    with pytest.raises(ServiceError, match="새 커밋"):
        await retry_review(github, review_id, "owner")


# GitHub App의 저장소 접근 권한이 없어지면 대시보드 접근을 막고 기존 리뷰 설정은 보존하는지 확인한다.
async def test_access_removal_blocks_dashboard_and_preserves_review_settings(github):
    review_id = await enqueue(github, 20, 1, "original", "automatic")
    github.active = False
    with pytest.raises(ServiceError):
        await repository_access(github, 20, "owner")
    with transaction() as db:
        assert db.get(Repository, 20).active is False
        assert db.get(Review, review_id).settings is not None


# public 저장소라도 명시적인 저장소 권한이 없는 사용자의 대시보드 접근은 거부하는지 확인한다.
async def test_public_readability_does_not_grant_dashboard_access(github):
    with transaction() as db:
        db.get(Repository, 20).private = False
    github.permission_value = "none"
    with pytest.raises(ServiceError) as error:
        await repository_access(github, 20, "outsider")
    assert error.value.status == 403


# 로그인하지 않은 조회·재시도 요청과 유효하지 않은 OAuth state를 거부하는지 확인한다.
def test_unauthenticated_requests_and_invalid_oauth_state_are_rejected(github):
    with TestClient(app) as client:
        assert client.get("/api/reviews?repository_id=20").status_code == 401
        assert client.post("/api/reviews/unknown/retry").status_code == 401
        assert client.get("/api/auth/callback?code=x&state=y").status_code == 400


# 수동 리뷰 중 head가 바뀌면 결과 게시를 막고 진행 댓글에 중단과 새 리뷰 요청 방법을 안내하는지 확인한다.
async def test_new_head_during_manual_review_finishes_progress_comment(github, monkeypatch):
    review_id = await enqueue(github, 20, 1, "new-head", "manual", "owner")

    async def changed(*args):
        github.head = "head2"
        return ReviewResult()

    monkeypatch.setattr(runner, "judge", changed)
    await execute(github, review_id)
    assert github.remote_reviews == []
    assert "실패" in github.comments[0]["body"]
    assert "새 리뷰" in github.comments[0]["body"]
    with transaction() as db:
        assert db.get(Review, review_id).status == "superseded"
