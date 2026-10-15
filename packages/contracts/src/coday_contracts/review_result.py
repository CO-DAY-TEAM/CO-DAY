# 리뷰 결과(ReviewResult) 계약 스키마
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["bug", "security", "style", "maintainability"]
    importance: Literal["important", "minor"]
    title: str = Field(min_length=1, max_length=180)
    path: str
    line: int = Field(ge=1)
    side: Literal["LEFT", "RIGHT"]
    start_line: int | None
    suggestion: str | None = Field(description="정확한 교체 코드만. 불확실하면 null")
    condition: str = Field(min_length=1, max_length=1200, description="한국어: 문제 발생 조건")
    evidence: str = Field(min_length=1, max_length=1600, description="한국어: 판단의 코드 근거")
    recommendation: str = Field(
        min_length=1,
        max_length=1200,
        description="한국어: 수정 방향 설명. 교체 코드는 suggestion에만 작성",
    )


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list)
