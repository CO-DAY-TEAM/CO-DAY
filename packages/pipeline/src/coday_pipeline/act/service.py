# 리뷰 결과를 GitHub PR에 게시
import hashlib

from coday_contracts.review_input import ReviewInput
from coday_contracts.review_result import ReviewResult
from coday_core.config import Settings
from coday_core.db import transaction
from coday_core.db.models import PostedFinding, PullRequest, Review
from coday_core.errors import ServiceError
from coday_core.github import GitHub, repo_path
from sqlalchemy import select

CATEGORIES = {
    "bug": "버그",
    "security": "보안",
    "style": "스타일",
    "maintainability": "유지보수성",
}


def plain(text: str) -> str:
    # 설명에 있는 HTML을 escape하고 @mention이 알림을 보내지 않도록 처리한다.
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("@", "@\u200b")


def build_publication(review: Review, result: ReviewResult, inputs: ReviewInput):
    summary = f"## CO-DAY 리뷰\n\n분석 커밋: `{review.head_sha[:12]}`\n\n"
    summary += f"분석 파일 **{len(inputs.analyzed_files)}개** · 제외 파일 **{len(inputs.excluded_files)}개**\n\n"
    if not inputs.chunks:
        summary += "리뷰 대상 없음: 제외 규칙 적용 후 분석할 텍스트 변경이 없습니다.\n"
    elif not result.findings:
        summary += "지적 없음: 분석 범위에서 게시할 문제를 발견하지 못했습니다.\n"
    if inputs.excluded_files:
        summary += "\n<details><summary>제외 파일과 사유</summary>\n\n"
        for path, reason in inputs.excluded_files.items():
            summary += f"- {plain(path)}: {plain(reason)}\n"
        summary += "\n</details>\n"
    batches, comments, metadata, length = [], [], [], len(summary)
    body = summary
    seen = set()
    for position, finding in enumerate(result.findings):
        # 이번 리뷰 결과 안에서 완전히 같은 지적만 제거하고, 이전 리뷰와는 비교하지 않는다.
        signature = finding.model_dump_json()
        if signature in seen:
            continue
        seen.add(signature)
        # 리뷰 실행 ID와 결과 내 위치로 각 게시 항목의 fingerprint를 만든다.
        key = hashlib.sha256(f"{review.id}:{position}".encode()).hexdigest()
        text = f"**[{CATEGORIES[finding.category]}] {plain(finding.title)}**"
        for label, value in (
            ("발생 조건", finding.condition),
            ("코드 근거", finding.evidence),
            ("수정 방향", finding.recommendation),
        ):
            text += f"\n\n**{label}**\n\n{plain(value)}"
        if finding.suggestion is not None and finding.importance == "important":
            text += f"\n\n```suggestion\n{finding.suggestion}\n```"
        if len(comments) >= 40 or length + len(text) > 50000:
            batches.append(
                {
                    "body": body,
                    "comments": comments,
                    "findings": metadata,
                    "github_id": None,
                }
            )
            body, comments, metadata, length = "## CO-DAY 리뷰 · 계속\n", [], [], 0
        metadata.append({"fingerprint": key, "category": finding.category})
        if finding.importance == "minor":
            body += f"\n### {plain(finding.path)}:{finding.line}\n{text}\n"
        else:
            comment = {
                "path": finding.path,
                "line": finding.line,
                "side": finding.side,
                "body": text,
            }
            if finding.start_line and finding.start_line < finding.line:
                comment.update(start_line=finding.start_line, start_side=finding.side)
            comments.append(comment)
        length += len(text)
    batches.append({"body": body, "comments": comments, "findings": metadata, "github_id": None})
    if any(len(batch["body"]) > 60000 for batch in batches):
        raise ServiceError("publication_limit", "리뷰 요약이 GitHub 게시 크기 한도를 넘었습니다.")
    for index, batch in enumerate(batches):
        batch["marker"] = f"<!-- coday:review:{review.id}:{index} -->"
        batch["body"] += "\n\n" + batch["marker"]
    return batches


async def progress(
    github: GitHub,
    token: str,
    full_name: str,
    review: Review,
    state: str,
    settings: Settings,
    detail: str = "",
):
    marker = f"<!-- coday:progress:{review.repository_id}:{review.pr_number} -->"
    link = f"{settings.public_url.rstrip('/')}/?review={review.id}"
    body = f"{marker}\n## CO-DAY · {state}\n\n커밋 `{review.head_sha[:12]}`\n\n{detail}"
    if state == "실패":
        body += f"\n\n[대시보드에서 확인하고 재시도하기]({link})"
    root = repo_path(full_name)
    with transaction() as db:
        pull = db.get(PullRequest, (review.repository_id, review.pr_number))
        comment_id = pull.progress_comment_id
    if not comment_id:
        comments = await github.pages(token, f"{root}/issues/{review.pr_number}/comments")
        own = [
            c
            for c in comments
            if c.get("user", {}).get("login") == settings.bot_login and marker in c.get("body", "")
        ]
        if own:
            comment_id = own[0]["id"]
    if comment_id:
        response = await github.request(
            token,
            "PATCH",
            f"{root}/issues/comments/{comment_id}",
            data={"body": body},
            allow_missing=True,
        )
        if response is None:
            comment_id = None
    if not comment_id:
        response = await github.request(
            token,
            "POST",
            f"{root}/issues/{review.pr_number}/comments",
            data={"body": body},
        )
        comment_id = response["id"]
    with transaction() as db:
        db.get(
            PullRequest, (review.repository_id, review.pr_number)
        ).progress_comment_id = comment_id


async def act(github: GitHub, token: str, full_name: str, review_id: str, guard):
    await guard()
    with transaction() as db:
        review = db.get(Review, review_id)
        previous_runs = list(
            db.scalars(
                select(Review).where(
                    Review.repository_id == review.repository_id,
                    Review.pr_number == review.pr_number,
                    Review.publication.is_not(None),
                )
            )
        )
    root = f"{repo_path(full_name)}/pulls/{review.pr_number}/reviews"
    remote_reviews = await github.pages(token, root)
    # 이전 실행의 게시 응답이 유실된 뒤 superseded가 되어도 통계용 게시 기록을 복구한다.
    # 복구한 기록은 현재 리뷰의 지적을 제외하는 데 사용하지 않는다.
    for old in previous_runs:
        for index, batch in enumerate(old.publication or []):
            if batch["github_id"]:
                continue
            posted = next(
                (
                    item
                    for item in remote_reviews
                    if item.get("user", {}).get("login") == github.settings.bot_login
                    and batch["marker"] in item.get("body", "")
                    and item.get("state") == "COMMENTED"
                    and item.get("commit_id") == old.head_sha
                ),
                None,
            )
            if posted:
                record_publication(old.id, index, posted["id"])
    with transaction() as db:
        review = db.get(Review, review_id)
        if review.publication is None:
            review.publication = build_publication(
                review,
                ReviewResult.model_validate(review.result),
                ReviewInput.model_validate(review.input),
            )
        plan = review.publication
    for index, batch in enumerate(plan):
        await guard()
        if batch["github_id"]:
            continue
        remote_reviews = await github.pages(token, root)
        posted = next(
            (
                item
                for item in remote_reviews
                if item.get("user", {}).get("login") == github.settings.bot_login
                and batch["marker"] in item.get("body", "")
                and item.get("state") == "COMMENTED"
                and item.get("commit_id") == review.head_sha
            ),
            None,
        )
        if not posted:
            await guard()
            posted = await github.request(
                token,
                "POST",
                root,
                data={
                    "commit_id": review.head_sha,
                    "event": "COMMENT",
                    "body": batch["body"],
                    "comments": batch["comments"],
                },
            )
        record_publication(review_id, index, posted["id"])


def record_publication(review_id: str, index: int, github_id: int):
    with transaction() as db:
        current = db.get(Review, review_id)
        updated = [dict(item) for item in current.publication]
        updated[index]["github_id"] = github_id
        current.publication = updated
        for item in updated[index]["findings"]:
            key = (current.repository_id, current.pr_number, item["fingerprint"])
            if not db.get(PostedFinding, key):
                db.add(
                    PostedFinding(
                        repository_id=current.repository_id,
                        pr_number=current.pr_number,
                        fingerprint=item["fingerprint"],
                        category=item["category"],
                        github_review_id=github_id,
                    )
                )
