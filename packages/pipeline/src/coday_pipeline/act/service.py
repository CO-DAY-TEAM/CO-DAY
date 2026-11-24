# 리뷰 결과를 GitHub PR에 게시
import hashlib
import re
from collections import Counter

from coday_contracts import ReviewInput, ReviewResult
from coday_contracts.review_result import Finding
from coday_core.config import Settings
from coday_core.db import transaction
from coday_core.db.models import PostedFinding, PullRequest, Review
from coday_core.errors import ServiceError
from coday_core.github import GitHub, repo_path
from sqlalchemy import select

from coday_pipeline.act.markdown import (
    BADGE_BASE_URL,
    escape_prose_tildes,
    excluded_file_row,
    render_review_badges,
)
from coday_pipeline.suggestion_conflicts import SEVERITY_ORDER, resolve_suggestion_conflicts

CATEGORIES = {
    "bug": "버그",
    "security": "보안",
    "performance": "성능",
    "style": "스타일",
    "maintainability": "유지보수성",
}


def plain(text: str) -> str:
    # 설명에 있는 HTML을 escape하고 @mention이 알림을 보내지 않도록 처리한다.
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("@", "@\u200b")


def review_text(text: str) -> str:
    return escape_prose_tildes(plain(text))


# 여러 줄 또는 블록으로 시작하는 필드는 각각의 Markdown 문단을 유지한다.
MARKDOWN_BLOCK_START = re.compile(
    r"^[ \t]|^(?:[#>~]|`{3,}|(?:[-+*]|[-*_]{3,}|\d{1,9}[.)])(?:\s|$))"
)


def build_inline_comment(finding: Finding, *, base_url: str = BADGE_BASE_URL) -> str:
    title = review_text(finding.title)
    try:
        badges = render_review_badges(finding.severity, finding.category, base_url=base_url)
    except ValueError:
        title = f"**[{CATEGORIES[finding.category]}] [{finding.severity}] {title}**"
    else:
        title = f"{badges}\n\n**{title}**"

    condition, evidence = finding.condition, finding.evidence
    block_content = any(
        "\n" in value or "\r" in value or MARKDOWN_BLOCK_START.match(value)
        for value in (condition, evidence)
    )
    separator = "\n\n" if block_content else " "
    explanation = separator.join((review_text(condition), review_text(evidence)))
    text = f"{title}\n\n{explanation}\n\n{review_text(finding.recommendation)}"
    if finding.suggestion is not None:
        text += f"\n\n```suggestion\n{finding.suggestion}\n```"
    return text


def build_review_body(review: Review, inputs: ReviewInput, counts: Counter[str]) -> str:
    excluded_count = len(inputs.excluded_files)
    summary = f"## CO-DAY 리뷰\n\n분석 커밋: `{review.head_sha[:12]}`\n\n"
    summary += f"분석 파일 **{len(inputs.files)}개** · 제외 파일 **{excluded_count}개**\n\n"
    total = counts.total()
    if total:
        summary += "### 📊 Review Summary\n\n| Severity | Count |\n|---|---:|\n"
        summary += "".join(f"| {severity} | {counts[severity]} |\n" for severity in SEVERITY_ORDER)
        summary += f"| **Total** | **{total}** |\n\n"
        summary += f"총 {total}건의 지적 사항을 발견했습니다. 상세 내용은 인라인 리뷰 댓글을 확인해 주세요."
    elif not inputs.files:
        summary += "이번 PR에는 리뷰 대상 파일이 없습니다."
    else:
        summary += "분석 범위에서 게시할 문제를 발견하지 못했습니다."
    if excluded_count:
        rows = "\n".join(
            excluded_file_row(path, reason) for path, reason in inputs.excluded_files.items()
        )
        summary += f"\n\n<details>\n<summary>제외 파일 ({excluded_count}개)</summary>\n\n"
        summary += f"{rows}\n\n</details>"
    return summary


def build_publication(review: Review, result: ReviewResult, inputs: ReviewInput):
    publication_result = resolve_suggestion_conflicts(result)
    comments, metadata = [], []
    counts: Counter[str] = Counter()
    seen = set()
    for position, finding in enumerate(publication_result.findings):
        # 이번 리뷰 결과 안에서 완전히 같은 지적만 제거하고, 이전 리뷰와는 비교하지 않는다.
        signature = result.findings[position].model_dump_json()
        if signature in seen:
            continue
        seen.add(signature)
        # 리뷰 실행 ID와 결과 내 위치로 각 게시 항목의 fingerprint를 만든다.
        key = hashlib.sha256(f"{review.id}:{position}".encode()).hexdigest()
        metadata.append({"fingerprint": key, "category": finding.category})
        comment = {
            "path": finding.path,
            "line": finding.line,
            "side": finding.side,
            "body": build_inline_comment(finding),
        }
        if finding.start_line and finding.start_line < finding.line:
            comment.update(start_line=finding.start_line, start_side=finding.side)
        comments.append(comment)
        counts[finding.severity] += 1
    summary = build_review_body(review, inputs, counts)
    if len(summary) > 60000:
        raise ServiceError("publication_limit", "리뷰 요약이 GitHub 게시 크기 한도를 넘었습니다.")
    marker = f"<!-- coday:review:{review.id} -->"
    return {
        "body": f"{summary}\n\n{marker}",
        "marker": marker,
        "comments": comments,
        "findings": metadata,
        "github_id": None,
    }


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
        if not old.publication:
            continue
        if old.publication["github_id"]:
            continue
        posted = next(
            (
                item
                for item in remote_reviews
                if item.get("user", {}).get("login") == github.settings.bot_login
                and old.publication["marker"] in item.get("body", "")
                and item.get("state") == "COMMENTED"
                and item.get("commit_id") == old.head_sha
            ),
            None,
        )
        if posted:
            record_publication(old.id, posted["id"])
    with transaction() as db:
        review = db.get(Review, review_id)
        if review.publication is None:
            review.publication = build_publication(
                review,
                ReviewResult.model_validate(review.result),
                ReviewInput.model_validate(review.input),
            )
        plan = review.publication
    await guard()
    if plan["github_id"]:
        return
    remote_reviews = await github.pages(token, root)
    posted = next(
        (
            item
            for item in remote_reviews
            if item.get("user", {}).get("login") == github.settings.bot_login
            and plan["marker"] in item.get("body", "")
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
                "body": plan["body"],
                "comments": plan["comments"],
            },
        )
    record_publication(review_id, posted["id"])


def record_publication(review_id: str, github_id: int):
    with transaction() as db:
        current = db.get(Review, review_id)
        current.publication = {**current.publication, "github_id": github_id}
        for item in current.publication["findings"]:
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
