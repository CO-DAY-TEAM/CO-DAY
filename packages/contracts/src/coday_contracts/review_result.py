# 리뷰 결과(ReviewResult) 계약 스키마
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["bug", "security", "performance", "maintainability", "style"]
    severity: Literal["P0", "P1", "P2", "P3"]
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

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_importance(cls, data):
        # 저장된 기존 결과를 읽기 위한 호환 처리이며, AI의 새 출력에는 severity만 사용한다.
        if isinstance(data, dict) and data.get("importance") in ("important", "minor"):
            data = dict(data)
            importance = data.pop("importance")
            data.setdefault("severity", "P1" if importance == "important" else "P3")
        return data


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list)
