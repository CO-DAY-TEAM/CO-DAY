# 분석된 파일과 diff 줄 정보의 계약 스키마
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# GitHub PR 파일 API의 status 값
FileStatus = Literal["added", "removed", "modified", "renamed", "copied", "changed", "unchanged"]

DiffLineKind = Literal["added", "removed", "context"]


class DiffLine(BaseModel):
    """diff의 한 줄. 줄 앞의 +, -, 공백 기호는 떼고 content에 코드만 담는다."""

    model_config = ConfigDict(frozen=True)  # 불변성 보장

    kind: DiffLineKind
    content: str
    old_line: int | None = Field(
        default=None, description="변경 전 파일 기준 줄 번호. 추가된 줄은 None"
    )
    new_line: int | None = Field(
        default=None, description="변경 후 파일 기준 줄 번호. 삭제된 줄은 None"
    )


class ParsedHunk(BaseModel):
    header: str  # @@ -10,4 +10,5 @@ def add
    lines: list[DiffLine]


class AnalyzedFile(BaseModel):
    """판단 단계에 넘길 한 파일의 전체 hunk와 줄 정보."""

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(min_length=1)
    status: FileStatus
    hunks: list[ParsedHunk] = Field(min_length=1)
