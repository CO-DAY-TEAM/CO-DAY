from pydantic import BaseModel, Field

from coday_contracts.analyzed_chunk import AnalyzedChunk


class ReviewInput(BaseModel):
    chunks: list[AnalyzedChunk] = Field(default_factory=list)
    analyzed_files: list[str] = Field(default_factory=list)
    excluded_files: dict[str, str] = Field(default_factory=dict)
    related_files: dict[str, str] = Field(default_factory=dict)
