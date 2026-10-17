# API 서버 애플리케이션 진입점
from fastapi import FastAPI

from apps.api.src.coday_api.schemas import ReviewCommentRequest
from coday_pipeline.act.service import register_manual_comment

app = FastAPI(title="CO-DAY API")

@app.post("/dev/review-comments", status_code=201)
def create_review_comment(request: ReviewCommentRequest):
    return register_manual_comment(
        owner=request.owner,
        repo=request.repo,
        pr_number=request.pr_number,
        commit_id=request.commit_id,
        path=request.path,
        start_line=request.start_line,
        end_line=request.end_line,
        side=request.side,
        body=request.body,
    )