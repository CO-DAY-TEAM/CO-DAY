from pydantic import BaseModel, Field

from coday_contracts.analyzed_file import AnalyzedFile


class FunctionFragment(BaseModel):
    start_line: int
    end_line: int
    code: str


class FunctionContext(BaseModel):
    path: str
    head_sha: str
    start_line: int
    end_line: int
    complete: bool = True
    fragments: list[FunctionFragment] = Field(default_factory=list)
    diff_ranges: list[tuple[int, int]] = Field(default_factory=list)
    complete_with_diff: bool = False


class ReviewInput(BaseModel):
    pr_title: str = ""
    pr_body: str = ""
    files: list[AnalyzedFile] = Field(default_factory=list)
    excluded_files: dict[str, str] = Field(default_factory=dict)
    related_files: dict[str, str] = Field(default_factory=dict)
    function_context: list[FunctionContext] = Field(default_factory=list)
