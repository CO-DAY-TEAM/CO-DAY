# 수집 → diff 파싱 → chunk 분할 순서로 분석 입력을 구성
from coday_contracts.review_input import ReviewInput
from coday_contracts.review_job import ReviewJob
from coday_contracts.settings import ReviewSettings
from coday_core.errors import ServiceError
from coday_core.github import GitHub

from coday_pipeline.analyze.chunker import chunks
from coday_pipeline.analyze.collector import collect
from coday_pipeline.analyze.diff_parser import parse_patch


async def analyze(
    job: ReviewJob, settings: ReviewSettings, github: GitHub, token: str, guard
) -> ReviewInput:
    collected = await collect(job, settings, github, token, guard)
    output = ReviewInput(
        excluded_files=collected.excluded_files,
        related_files=collected.related_files,
    )
    for file in collected.files:
        hunks = parse_patch(file.patch)
        # GitHub의 변경 줄 수와 비교해 patch가 일부만 제공된 경우 완료로 처리하지 않는다.
        additions = sum(line.kind == "added" for hunk in hunks for line in hunk.lines)
        deletions = sum(line.kind == "removed" for hunk in hunks for line in hunk.lines)
        if (additions, deletions) != (file.additions, file.deletions):
            raise ServiceError(
                "incomplete_diff", f"GitHub에서 {file.path}의 전체 변경 내용을 가져오지 못했습니다."
            )
        parts = chunks(file.path, file.status, hunks, github.settings.chunk_chars)
        if parts:
            output.chunks.extend(parts)
            output.analyzed_files.append(file.path)
    return output
