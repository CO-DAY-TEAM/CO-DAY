from pydantic import BaseModel, Field

from coday_contracts.analyzed_file import AnalyzedFile


class ReviewInput(BaseModel):
    files: list[AnalyzedFile] = Field(default_factory=list)
    excluded_files: dict[str, str] = Field(default_factory=dict)
    related_files: dict[str, str] = Field(default_factory=dict)
