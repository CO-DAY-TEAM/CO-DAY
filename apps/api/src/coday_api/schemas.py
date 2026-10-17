from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReviewCommentRequest(BaseModel):
    owner: str = Field(default="CO-DAY-TEAM", min_length=1)
    repo: str = Field(default="CO-WORK", min_length=1)
    pr_number: int = Field(gt=0)
    commit_id: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    path: str = Field(min_length=1)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    side: Literal["LEFT", "RIGHT"] = "RIGHT"
    body: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_line_range(self):
        if self.start_line > self.end_line:
            raise ValueError("시작 줄은 끝 줄보다 클 수 없습니다.")

        return self