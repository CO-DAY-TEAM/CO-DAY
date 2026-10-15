import pytest
from coday_contracts.review_input import ReviewInput
from coday_contracts.review_result import ReviewResult
from coday_core.db.models import Review
from coday_pipeline.act.service import build_publication


def finding_data(**updates):
    return {
        "category": "security",
        "importance": "important",
        "title": "URL scheme 검증 누락",
        "condition": "사용자가 작성한 링크를 클릭하면 발생합니다.",
        "evidence": "`href`에 허용하지 않은 URL scheme도 들어갈 수 있습니다.",
        "recommendation": "허용한 URL scheme에 해당하는 링크만 생성하세요.",
        "path": "links.ts",
        "line": 1,
        "side": "RIGHT",
        "start_line": None,
        "suggestion": None,
        **updates,
    }


# 댓글의 설명 문단을 구성하고, suggestion이 있을 때만 교체 코드를 한 번 표시하는지 확인한다.
@pytest.mark.parametrize(
    "suggestion", [None, "const parsed = new URL(href);\nreturn parsed.protocol;"]
)
def test_server_renders_sections_and_only_one_suggestion(suggestion):
    result = ReviewResult.model_validate({"findings": [finding_data(suggestion=suggestion)]})
    batches = build_publication(
        Review(id="test", head_sha="head"), result, ReviewInput(analyzed_files=["links.ts"])
    )
    body = batches[0]["comments"][0]["body"]
    assert all(label in body for label in ("발생 조건", "코드 근거", "수정 방향"))
    assert "`href`" in body
    assert "suggestion: null" not in body
    assert body.count("```suggestion") == (0 if suggestion is None else 1)
    if suggestion:
        assert body.count(suggestion) == 1
