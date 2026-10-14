# 리뷰 작업(ReviewJob) 계약 스키마
from pydantic import BaseModel, ConfigDict, Field


class ReviewJob(BaseModel):
    """리뷰할 PR 하나를 가리키는 작업. 수신 단계가 만들고 분석 단계가 받는다."""

    model_config = ConfigDict(frozen=True)

    owner: str = Field(min_length=1, description="저장소 주인 (예: CO-DAY-TEAM)")
    repo: str = Field(min_length=1, description="저장소 이름 (예: CO-WORK)")
    pr_number: int = Field(gt=0, description="PR 번호")
    head_sha: str = Field(min_length=1, description="리뷰할 head 커밋 SHA")

    # 아래는 수신 단계를 붙일 때 채울 필드. 수신 없이 분석만 돌릴 때는 None
    base_sha: str | None = Field(default=None, description="비교 기준 base 커밋 SHA")
    installation_id: int | None = Field(default=None, description="GitHub App 설치 ID (App 인증용)")
    delivery_id: str | None = Field(default=None, description="웹훅 전달 ID (중복 이벤트 처리용)")
