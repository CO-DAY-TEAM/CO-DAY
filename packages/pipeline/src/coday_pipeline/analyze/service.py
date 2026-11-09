# 수집 → diff 파싱·검증 → 파일별로 묶어 전체 PR 입력 구성
from coday_contracts import AnalyzedFile, ReviewInput, ReviewJob, ReviewSettings
from coday_core.errors import ServiceError
from coday_core.github import GitHub

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
        if additions or deletions:
            output.files.append(AnalyzedFile(file_path=file.path, status=file.status, hunks=hunks))
    return output
