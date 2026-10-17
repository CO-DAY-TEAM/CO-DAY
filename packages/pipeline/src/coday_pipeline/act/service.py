# 리뷰 결과를 GitHub PR에 게시
from coday_core.config import github_app_id, github_private_key_path
from coday_core.github import (
    create_app_jwt,
    create_installation_token,
    get_installation_id,
    post_review_comment,
)


def register_manual_comment(
    owner: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    path: str,
    start_line: int,
    end_line: int,
    side: str,
    body: str,
) -> dict:
    app_jwt = create_app_jwt(
        app_id=github_app_id,
        private_key_path=github_private_key_path,
    )

    installation_id = get_installation_id(
        app_jwt=app_jwt,
        owner=owner,
        repo=repo,
    )

    installation_token = create_installation_token(
        app_jwt=app_jwt,
        installation_id=installation_id,
        repo=repo,
    )

    comment = post_review_comment(
        installation_token=installation_token,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        commit_id=commit_id,
        path=path,
        start_line=start_line,
        end_line=end_line,
        side=side,
        body=body,
    )

    return {
        "comment_id": str(comment["id"]),
        "html_url": comment["html_url"],
    }