import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from coday_contracts import AnalyzedFile, DiffLine, Finding, ParsedHunk, ReviewInput, ReviewResult
from coday_core.config import Settings
from coday_core.errors import ServiceError
from coday_pipeline.judge import service


@pytest.fixture
def inputs():
    return ReviewInput(
        files=[
            AnalyzedFile(
                file_path=path,
                status="modified",
                hunks=[
                    ParsedHunk(
                        header=f"@@ -{start},1 +{start},2 @@",
                        lines=[
                            DiffLine(
                                kind="context", content="value = 0", old_line=start, new_line=start
                            ),
                            DiffLine(kind="added", content=code, new_line=start + 1),
                        ],
                    )
                ],
            )
            for path, code, start in [("a.py", "x = 1", 2), ("b.py", "y = 2", 4)]
        ],
        related_files={"context.py": "value = 0"},
    )


def finding(path, line=3, start_line=None):
    return Finding(
        category="bug",
        importance="important",
        title="a",
        condition="발생 조건",
        evidence="코드 근거",
        recommendation="수정 방향",
        path=path,
        line=line,
        side="RIGHT",
        start_line=start_line,
        suggestion=None,
    )


# 파일별로 변경 줄과 수정 범위를 검증한다. b.py의 5행도 a.py에서는 허용하지 않는다.
@pytest.mark.parametrize(
    ("path", "line", "start_line"),
    [("elsewhere.py", 3, None), ("a.py", 2, None), ("a.py", 5, None), ("a.py", 3, 1)],
    ids=["unknown-file", "context-line", "line-from-other-file", "range-outside-input"],
)
def test_finding_outside_reviewed_changes_is_rejected(inputs, path, line, start_line):
    result = ReviewResult(findings=[finding(path, line, start_line)])
    with pytest.raises(ServiceError):
        service.validate_findings(result, inputs)


# 전체 입력을 한 번에 전달하고 두 파일의 지적을 모두 반환한다. 실제 API는 호출하지 않는다.
async def test_judge_reviews_all_files_in_one_call(inputs, monkeypatch):
    output = ReviewResult(findings=[finding("a.py"), finding("b.py", line=5)])
    run = AsyncMock(return_value=SimpleNamespace(final_output=output))
    reserve = AsyncMock()
    monkeypatch.setattr(service.Runner, "run", run)
    settings = Settings(_env_file=None, openai_api_key="test-key")

    result = await service.judge(inputs, "리뷰 지침", settings, reserve)

    run.assert_awaited_once()
    payload = json.loads(run.call_args.kwargs["input"])
    assert payload["files"] == [file.model_dump() for file in inputs.files]
    assert result == output
