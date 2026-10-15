import pytest
from coday_contracts.review_result import ReviewResult
from coday_core.errors import ServiceError
from coday_pipeline.analyze.chunker import chunks
from coday_pipeline.analyze.diff_parser import parse_patch
from coday_pipeline.judge.service import validate_findings


# 분석한 파일과 다른 path를 가리키는 지적은 거부하는지 확인한다.
def test_finding_outside_analyzed_file_is_rejected():
    chunk = chunks("a.py", "added", parse_patch("@@ -0,0 +1 @@\n+x = 1\n"), 1000)[0]
    result = ReviewResult.model_validate(
        {
            "findings": [
                {
                    "category": "bug",
                    "importance": "important",
                    "title": "a",
                    "condition": "발생 조건",
                    "evidence": "코드 근거",
                    "recommendation": "수정 방향",
                    "path": "elsewhere.py",
                    "line": 1,
                    "side": "RIGHT",
                    "start_line": None,
                    "suggestion": None,
                }
            ]
        }
    )
    with pytest.raises(ServiceError):
        validate_findings(result, chunk)
